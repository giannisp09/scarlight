"""Engagement-scope authorization guard for Scarlight.

Scarlight is an offensive-security tool. Every engagement that drives the
agent's turn loop must have an authorization scope on file — a YAML
``engagement.yaml`` declaring authorized targets, a human-readable
authorization reference (contract / bug-bounty program / lab), and an
operator acknowledgment of ``CODE_OF_USE.md``. The pre-flight check sits
at ``AIAgent.run_conversation()``; with no valid scope, the turn refuses.

Discovery order (first match wins):

1. ``SCARLIGHT_ENGAGEMENT`` env var — absolute path to a YAML file.
2. ``./engagement.yaml`` in the current working directory.
3. ``<SCARLIGHT_HOME>/engagement.yaml`` (default ``~/.scarlight/``).

Bypass: ``SCARLIGHT_NO_ENGAGEMENT=1`` skips the guard with a warning
logged once per process. Reserved for internal harnesses (batch_runner,
rl_cli, mini_swe_runner) and the test suite — NOT for production
engagements. See ``CODE_OF_USE.md`` and ``engagement.yaml.example``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from scarlight_constants import get_scarlight_home


_BYPASS_ENV_VAR = "SCARLIGHT_NO_ENGAGEMENT"
_OVERRIDE_ENV_VAR = "SCARLIGHT_ENGAGEMENT"
_TERMINAL_ENV_VAR = "TERMINAL_ENV"
_TERMINAL_DEFAULT_FOR_ENGAGEMENT = "docker"
_CWD_FILENAME = "engagement.yaml"
_HOME_FILENAME = "engagement.yaml"
_EXAMPLE_PATH_HINT = "engagement.yaml.example"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Set true once we've logged the bypass-active warning so we don't spam
# the logs every turn. Reset only by interpreter restart.
_bypass_warned: bool = False

# Set true once we've logged the sandbox-default warning per process —
# operators only need to see "I defaulted you to Docker" once.
_sandbox_default_logged: bool = False


class EngagementScopeError(RuntimeError):
    """Raised when an engagement starts without a valid authorization scope."""


@dataclass(frozen=True)
class EngagementScope:
    """A loaded, validated authorization scope for a Scarlight engagement.

    Treat this as an immutable record of the operator's declared authority
    to test a set of targets. Future tooling may use ``.targets`` and
    ``.is_target_authorized()`` to gate per-tool actions; v1 only uses
    its presence as a pre-flight check.
    """

    engagement_id: str
    authorization_reference: str
    operator: str
    acknowledged_at: str
    targets: Tuple[str, ...]
    code_of_use_version: Optional[str] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    notes: Optional[str] = None
    source_path: Optional[Path] = None
    bypassed: bool = False
    raw: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def summary_line(self) -> str:
        """One-line operator-facing description for logs / banners."""
        if self.bypassed:
            return f"engagement: bypassed via {_BYPASS_ENV_VAR}=1"
        target_count = len(self.targets)
        target_word = "target" if target_count == 1 else "targets"
        return (
            f"engagement: {self.engagement_id} "
            f"({target_count} {target_word}; auth: {self.authorization_reference})"
        )


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in _TRUTHY


def _bypass_active() -> bool:
    val = os.environ.get(_BYPASS_ENV_VAR, "").strip()
    return bool(val) and _is_truthy(val)


def _bypass_scope() -> EngagementScope:
    return EngagementScope(
        engagement_id="bypass:no-engagement",
        authorization_reference=(
            f"{_BYPASS_ENV_VAR}=1 set; engagement guard bypassed for "
            f"internal harness / test use"
        ),
        operator=os.environ.get("USER", "unknown"),
        acknowledged_at="",
        targets=(),
        bypassed=True,
    )


def _warn_bypass_once() -> None:
    global _bypass_warned
    if _bypass_warned:
        return
    _bypass_warned = True
    logging.warning(
        "Engagement authorization guard bypassed: %s=1 is set. "
        "This is for internal harness / test use only. Production "
        "engagements MUST run with a valid engagement.yaml — see "
        "CODE_OF_USE.md.",
        _BYPASS_ENV_VAR,
    )


def _candidate_paths() -> List[Path]:
    """Return discovery paths in precedence order. Does not check existence."""
    paths: List[Path] = []
    override = os.environ.get(_OVERRIDE_ENV_VAR, "").strip()
    if override:
        paths.append(Path(override).expanduser())
    paths.append(Path.cwd() / _CWD_FILENAME)
    paths.append(get_scarlight_home() / _HOME_FILENAME)
    return paths


def _parse_iso8601(value: Any, field_name: str) -> datetime:
    """Parse an ISO-8601 string into a tz-aware UTC datetime. Raises on bad input."""
    if not isinstance(value, str) or not value.strip():
        raise EngagementScopeError(
            f"engagement scope field {field_name!r} must be an ISO-8601 datetime string"
        )
    text = value.strip()
    # ``datetime.fromisoformat`` accepts ``Z`` only on Python 3.11+; normalize.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EngagementScopeError(
            f"engagement scope field {field_name!r} is not valid ISO-8601: {value!r} ({exc})"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate(raw: Dict[str, Any], source: Path) -> EngagementScope:
    """Validate raw YAML data, return an EngagementScope. Raises on failure."""

    def _require_str(key: str) -> str:
        v = raw.get(key)
        if not isinstance(v, str) or not v.strip():
            raise EngagementScopeError(
                f"engagement scope at {source} is missing required string field "
                f"{key!r} (or the value is empty)"
            )
        return v.strip()

    engagement_id = _require_str("engagement_id")
    authorization_reference = _require_str("authorization_reference")

    ack = raw.get("operator_acknowledgment")
    if not isinstance(ack, dict):
        raise EngagementScopeError(
            f"engagement scope at {source} is missing the "
            f"'operator_acknowledgment' block (mapping with 'acknowledged: "
            f"true', 'operator', 'date')"
        )
    if ack.get("acknowledged") is not True:
        raise EngagementScopeError(
            f"engagement scope at {source}: 'operator_acknowledgment.acknowledged' "
            f"must be literal `true` — operator must acknowledge CODE_OF_USE.md"
        )
    operator = ack.get("operator")
    if not isinstance(operator, str) or not operator.strip():
        raise EngagementScopeError(
            f"engagement scope at {source}: 'operator_acknowledgment.operator' "
            f"is required (who is running this engagement)"
        )
    ack_date = ack.get("date")
    if not isinstance(ack_date, str) or not str(ack_date).strip():
        # Accept date objects from YAML's native date parsing too.
        if hasattr(ack_date, "isoformat"):
            ack_date = ack_date.isoformat()
        else:
            raise EngagementScopeError(
                f"engagement scope at {source}: 'operator_acknowledgment.date' "
                f"is required (when the operator acknowledged the policy)"
            )

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise EngagementScopeError(
            f"engagement scope at {source}: 'targets' must be a non-empty list of "
            f"hostnames, IPs, CIDR ranges, or URLs you are authorized to test"
        )
    targets: List[str] = []
    for i, t in enumerate(targets_raw):
        if not isinstance(t, str) or not t.strip():
            raise EngagementScopeError(
                f"engagement scope at {source}: 'targets[{i}]' must be a non-empty string"
            )
        targets.append(t.strip())

    window = raw.get("window") or {}
    if not isinstance(window, dict):
        raise EngagementScopeError(
            f"engagement scope at {source}: 'window' must be a mapping with "
            f"optional 'start' and 'end' ISO-8601 datetimes"
        )
    window_start = (
        _parse_iso8601(window["start"], "window.start") if "start" in window else None
    )
    window_end = (
        _parse_iso8601(window["end"], "window.end") if "end" in window else None
    )
    now = datetime.now(tz=timezone.utc)
    if window_start is not None and window_start > now:
        raise EngagementScopeError(
            f"engagement scope at {source}: window.start is in the future "
            f"({window_start.isoformat()}) — engagement has not begun yet"
        )
    if window_end is not None and window_end < now:
        raise EngagementScopeError(
            f"engagement scope at {source}: window.end is in the past "
            f"({window_end.isoformat()}) — engagement window has expired"
        )

    code_of_use_version = ack.get("code_of_use_version")
    if code_of_use_version is not None and not isinstance(code_of_use_version, str):
        code_of_use_version = str(code_of_use_version)

    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)

    return EngagementScope(
        engagement_id=engagement_id,
        authorization_reference=authorization_reference,
        operator=operator.strip(),
        acknowledged_at=str(ack_date).strip(),
        targets=tuple(targets),
        code_of_use_version=code_of_use_version,
        window_start=window_start,
        window_end=window_end,
        notes=notes,
        source_path=source,
        bypassed=False,
        raw=dict(raw),
    )


def load_active_scope() -> Optional[EngagementScope]:
    """Find, parse, and validate the active engagement scope.

    Returns the validated :class:`EngagementScope` or ``None`` if no
    scope file exists at any candidate path. Raises
    :class:`EngagementScopeError` if a file exists but fails validation
    (so a misconfigured file refuses loudly, never silently).
    """
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise EngagementScopeError(
                f"engagement scope at {path} is not valid YAML: {exc}"
            ) from exc
        if raw is None:
            raise EngagementScopeError(
                f"engagement scope at {path} is empty — see {_EXAMPLE_PATH_HINT}"
            )
        if not isinstance(raw, dict):
            raise EngagementScopeError(
                f"engagement scope at {path} must be a YAML mapping, got "
                f"{type(raw).__name__} — see {_EXAMPLE_PATH_HINT}"
            )
        return _validate(raw, path)
    return None


def _refusal_message() -> str:
    home = get_scarlight_home()
    searched = "\n".join(f"  - {p}" for p in _candidate_paths())
    return (
        "Refused to start engagement: no authorization scope configuration found.\n"
        "\n"
        "Scarlight is an offensive-security tool. Every engagement must have a\n"
        "valid engagement.yaml declaring authorized targets, an authorization\n"
        "reference, and operator acknowledgment of CODE_OF_USE.md.\n"
        "\n"
        "Searched (in precedence order):\n"
        f"{searched}\n"
        "\n"
        f"Fix one of:\n"
        f"  1. Copy {_EXAMPLE_PATH_HINT} to {home / _HOME_FILENAME} and fill it in.\n"
        f"  2. Copy {_EXAMPLE_PATH_HINT} to ./engagement.yaml for this working dir.\n"
        f"  3. Set {_OVERRIDE_ENV_VAR}=/path/to/engagement.yaml.\n"
        f"\n"
        f"Internal harnesses and the test suite may set {_BYPASS_ENV_VAR}=1\n"
        f"to bypass with a warning. Do not set this in production."
    )


def _operator_has_chosen_terminal_backend() -> bool:
    """Return True iff the operator has explicitly pinned a terminal
    backend. The schema default ``local`` being bridged into
    ``TERMINAL_ENV`` by ``cli.load_cli_config()`` at import time does NOT
    count as an operator choice — it's just the upstream default leaking
    through, and Scarlight's offensive-engagement default is Docker.

    Three ways the operator can pin:

    1. ``TERMINAL_ENV`` already set to anything other than ``local`` —
       impossible for ``cli.load_cli_config()`` to have produced from
       schema defaults, so it must have come from the shell, the dotenv
       loader, or another deliberate setter.
    2. ``TERMINAL_ENV`` line present in ``~/.scarlight/.env`` — written by
       ``scarlight config set terminal.backend`` or ``scarlight setup``.
    3. ``terminal.backend`` key present in the user's ``~/.scarlight/
       config.yaml`` — the documented config-file knob.

    Edge case: an operator who launches ``TERMINAL_ENV=local scarlight``
    from a shell without persisting that choice in ``.env`` or
    ``config.yaml`` will get overridden to Docker. That trade is
    deliberate — for Scarlight, sandbox-by-default beats preserving a
    bare-shell choice that visually matches the schema default.
    """
    current = os.environ.get(_TERMINAL_ENV_VAR, "").strip()
    if current and current != "local":
        return True

    from scarlight_constants import get_scarlight_home

    home = get_scarlight_home()
    env_file = home / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("TERMINAL_ENV="):
                    return True
        except OSError:
            pass

    cfg_file = home / "config.yaml"
    if cfg_file.is_file():
        try:
            with open(cfg_file, encoding="utf-8") as f:
                cfg_raw = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            cfg_raw = {}
        terminal_cfg = cfg_raw.get("terminal") if isinstance(cfg_raw, dict) else None
        if isinstance(terminal_cfg, dict) and "backend" in terminal_cfg:
            return True

    return False


def _enforce_sandboxed_terminal_default(scope: EngagementScope) -> None:
    """Default the terminal tool to the Docker (Kali) sandbox when a real
    engagement is active and the operator hasn't already chosen a backend.

    Step 5 sets the Kali image as ``DEFAULT_TERMINAL_IMAGE`` but leaves the
    default ``TERMINAL_ENV`` at ``local`` (hermes-agent's general-purpose
    default). For an offensive-security engagement that pairing is wrong:
    the scope guard (Step 7) clears the turn, but commands then run on the
    operator's host instead of inside the sandbox Step 5 declared as the
    execution substrate. This helper closes that gap.

    The tricky bit: by the time ``run_conversation`` calls us, ``cli.py``'s
    module-level ``load_cli_config()`` has already bridged the schema
    default ``terminal.backend: local`` into ``TERMINAL_ENV=local``. So we
    can't just check ``"TERMINAL_ENV" in os.environ`` — we need to ask
    "did the operator actually pin this, or is it the schema default
    bleeding through?". :func:`_operator_has_chosen_terminal_backend`
    answers that.

    Opt-out: set ``TERMINAL_ENV=local`` (or ``ssh`` / any other backend) in
    the shell before invoking Scarlight, or persist the choice via
    ``scarlight config set terminal.backend <backend>``. Bypassed scopes
    (``SCARLIGHT_NO_ENGAGEMENT=1``) are left untouched — internal harnesses
    and tests don't want their terminal tool quietly switched to Docker.
    """
    global _sandbox_default_logged

    if scope.bypassed:
        return
    if _operator_has_chosen_terminal_backend():
        return

    os.environ[_TERMINAL_ENV_VAR] = _TERMINAL_DEFAULT_FOR_ENGAGEMENT
    if _sandbox_default_logged:
        return
    _sandbox_default_logged = True
    logging.warning(
        "Engagement active: defaulting %s=%s so offensive commands run "
        "inside the Kali sandbox (fork-runbook Step 5). Override by "
        "setting %s explicitly or `scarlight config set terminal.backend "
        "<backend>`.",
        _TERMINAL_ENV_VAR,
        _TERMINAL_DEFAULT_FOR_ENGAGEMENT,
        _TERMINAL_ENV_VAR,
    )


def assert_active_scope() -> EngagementScope:
    """Load + validate the active scope, or refuse the engagement.

    Honors the ``SCARLIGHT_NO_ENGAGEMENT=1`` bypass for internal use.
    Otherwise raises :class:`EngagementScopeError` with an actionable
    message if no valid scope is found.

    On success with a real scope, defaults the terminal backend to Docker
    (Kali) if the operator hasn't pinned one — see
    :func:`_enforce_sandboxed_terminal_default`.
    """
    if _bypass_active():
        _warn_bypass_once()
        return _bypass_scope()

    scope = load_active_scope()
    if scope is None:
        raise EngagementScopeError(_refusal_message())
    _enforce_sandboxed_terminal_default(scope)
    return scope

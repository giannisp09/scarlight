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

import ipaddress
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

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

# Per-process cache of the currently-active EngagementScope. Populated by
# ``assert_active_scope()`` so tools (terminal, web, browser) can fetch the
# scope via :func:`get_active_scope` without re-reading the YAML on every
# call. Reset only by interpreter restart.
_active_scope: Optional["EngagementScope"] = None

# Network-target extraction patterns for parsing shell commands the
# terminal tool is about to execute. The goal is conservative: catch the
# obvious outbound targets (URLs, FQDN-shaped tokens, IPv4 and IPv6
# addresses) so per-target enforcement can apply. False positives produce
# extra refusal turns (the agent rephrases); false negatives let
# out-of-scope traffic through, so prefer to over-catch.
#
# URLs and FQDNs / IPv4 use regex; IPv6 is split out from the regex path
# and validated through ipaddress.ip_address per-token because IPv6 short
# notation (``::``, ``::1``, ``2001:db8::cafe``) interacts badly with
# regex word boundaries.
_URL_RE = re.compile(
    r"\bhttps?://[\w.\-]+(?::\d+)?(?:/[^\s'\"<>`]*)?",
    re.IGNORECASE,
)
_FQDN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Token splitter for the IPv6 pass: shell punctuation + whitespace.
_TOKEN_SPLIT_RE = re.compile(r"[\s;|&<>(){}\"'=,]+")


class EngagementScopeError(RuntimeError):
    """Raised when an engagement starts without a valid authorization scope."""


def _extract_host(value: str, allow_cidr: bool = False) -> str:
    """Pluck the canonical host (or CIDR if ``allow_cidr=True``) from a URL,
    ``host:port`` pair, bracketed IPv6, bare IPv6, or bare hostname.

    Returned host is lowercased and stripped. Returns ``""`` on any parse
    failure or empty input. This is intentionally permissive — the caller
    treats an empty return as "no host to enforce against" and moves on.
    """
    if not value or not isinstance(value, str):
        return ""
    s = value.strip().lower()
    if not s:
        return ""

    # URL form?
    if "://" in s:
        try:
            return (urlparse(s).hostname or "").lower()
        except Exception:
            return ""

    # CIDR like "10.0.0.0/24" or "2001:db8::/32" — only when the rule side
    # is being extracted (scope target). Try the raw string first so IPv6
    # CIDRs (which contain colons) parse cleanly; only if that fails do
    # we attempt to strip a trailing :port from an IPv4 CIDR like
    # "10.0.0.0/24:80" (an unusual scope notation but accept it).
    if "/" in s:
        if allow_cidr:
            try:
                ipaddress.ip_network(s, strict=False)
                return s
            except ValueError:
                base, sep, port = s.rpartition(":")
                if sep and port.isdigit():
                    try:
                        ipaddress.ip_network(base, strict=False)
                        return base
                    except ValueError:
                        pass
        # Path-without-scheme ("acme.com/foo") or CIDR-without-permission:
        # not a legitimate host. Refuse rather than guess.
        return ""

    # Bracketed IPv6: "[::1]:8080" → "::1"
    if s.startswith("[") and "]" in s:
        return s.split("]", 1)[0][1:]

    # Bare IPv6 (multiple colons, no slash, parses as an IP address)
    if s.count(":") > 1 and "/" not in s:
        try:
            ipaddress.ip_address(s)
            return s
        except ValueError:
            pass

    # host:port → host
    if ":" in s:
        return s.rsplit(":", 1)[0]

    return s


def _extract_network_targets_from_command(command: str) -> List[str]:
    """Find every plausible outbound network target in a shell command.

    Returns a sorted, deduplicated list of URLs, FQDN-shaped hostnames,
    IPv4 addresses, and IPv6 addresses. Used by the terminal-tool
    integration to per-call-enforce the engagement scope. Empty/non-string
    input returns ``[]``.

    Conservative-but-loose: prefers false positives (extra refusal turns
    the agent retries) over false negatives (out-of-scope traffic leaks).
    Tokens like ``hello.world`` will match the FQDN pattern; that's
    acceptable — the agent rephrases on the refusal.
    """
    if not command or not isinstance(command, str):
        return []
    found: set = set()

    # URL / FQDN / IPv4 via regex.
    for match in _URL_RE.findall(command):
        found.add(match)
    for match in _FQDN_RE.findall(command):
        found.add(match)
    for match in _IPV4_RE.findall(command):
        found.add(match)

    # IPv6 via tokenize + ipaddress validation. Regex on raw IPv6 with
    # word-boundaries doesn't handle ``::`` short form cleanly, so we
    # split the command on shell punctuation and ask the standard library
    # whether each colon-bearing token is a valid IP. Catches bracketed
    # forms like ``[::1]:8080`` by stripping brackets first.
    for tok in _TOKEN_SPLIT_RE.split(command):
        tok = tok.strip().rstrip(".,!?:")
        if not tok or ":" not in tok:
            continue
        # Bracketed IPv6 with optional port.
        if tok.startswith("[") and "]" in tok:
            inner = tok.split("]", 1)[0][1:]
            try:
                ipaddress.ip_address(inner)
                found.add(inner)
                continue
            except ValueError:
                pass
        # Bare IPv6 (multiple colons, parses as IP).
        if tok.count(":") >= 2:
            try:
                ipaddress.ip_address(tok)
                found.add(tok)
            except ValueError:
                pass

    return sorted(found)


@dataclass(frozen=True)
class EngagementScope:
    """A loaded, validated authorization scope for a Scarlight engagement.

    Treat this as an immutable record of the operator's declared authority
    to test a set of targets. :meth:`is_target_authorized` is consulted by
    the terminal, web, and browser tools to refuse out-of-scope dispatch.
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

    def is_target_authorized(self, url_or_host: str) -> bool:
        """Test whether a given URL, ``host:port``, or bare host falls inside
        the operator's declared scope.

        Matching rules (any one matching scope target returns True):

        - **Exact host** match, case-insensitive. ``acme.com`` in scope matches
          ``acme.com`` and ``https://acme.com/anything``; it does NOT match
          ``evil-acme.com`` (no substring) or ``sub.acme.com`` (no wildcard
          implied — list the subdomain explicitly).
        - **CIDR** match for IP candidates. ``10.0.0.0/24`` matches every
          host in that block, including ``http://10.0.0.5:8080/foo``. CIDR
          rules do NOT match hostnames — only IP literals (no DNS).
        - **Port-agnostic.** Scope ``acme.com:443`` and ``acme.com:80`` both
          collapse to ``acme.com`` for the purpose of host matching. If
          port-level restriction matters for your engagement, that
          enforcement lives elsewhere (a planned future hook).

        Bypassed scopes (``SCARLIGHT_NO_ENGAGEMENT=1``) always return True —
        internal harnesses and tests shouldn't have their tool calls
        refused. Empty input returns False (nothing to authorize).
        """
        if self.bypassed:
            return True
        candidate = _extract_host(url_or_host, allow_cidr=False)
        if not candidate:
            return False
        try:
            candidate_ip = ipaddress.ip_address(candidate)
        except ValueError:
            candidate_ip = None
        for target in self.targets:
            rule = _extract_host(target, allow_cidr=True)
            if not rule:
                continue
            if "/" in rule:
                if candidate_ip is None:
                    continue
                try:
                    if candidate_ip in ipaddress.ip_network(rule, strict=False):
                        return True
                except ValueError:
                    continue
            else:
                if rule == candidate:
                    return True
        return False


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


def _format_refusal_for_unauthorized(
    unauthorized: List[str], scope: "EngagementScope"
) -> str:
    """Build the operator-facing refusal message for an out-of-scope hit.

    Lists the offending target(s) first (truncated past 5), then the
    authorized scope (also truncated past 5), then the fix. Goes through
    a single helper so terminal, web, and browser refusals read the same.
    """
    def _trunc(items: List[str], cap: int = 5) -> str:
        shown = ", ".join(items[:cap])
        if len(items) > cap:
            shown += f" (and {len(items) - cap} more)"
        return shown

    return (
        "Refused: target(s) not in engagement scope. "
        f"Unauthorized: {_trunc(unauthorized)}. "
        f"Authorized per engagement.yaml: {_trunc(list(scope.targets))}. "
        "Edit the engagement's `targets:` list to allow, or hit only the "
        "currently-listed targets."
    )


def check_command_authorized(command: str) -> Optional[str]:
    """Check whether a shell command's network targets are all in scope.

    Used by ``tools/terminal_tool.py`` before executing any command — the
    Step 7 scope guard cleared the *turn*; this gate clears the *tool
    call*. The targets in the command (URLs, FQDN-looking tokens, IPv4,
    IPv6) are extracted by :func:`_extract_network_targets_from_command`
    and matched against the active scope.

    Returns ``None`` when:
      - there is no active scope (called outside an engagement),
      - the active scope is bypassed (``SCARLIGHT_NO_ENGAGEMENT=1``),
      - the command has no detectable network targets,
      - every detected target falls inside the scope.

    Returns the refusal-message string otherwise; callers shape that into
    whatever error envelope they emit. Logs at WARNING level on refusal.
    """
    scope = get_active_scope()
    if scope is None or scope.bypassed:
        return None
    targets = _extract_network_targets_from_command(command)
    if not targets:
        return None
    unauthorized = [t for t in targets if not scope.is_target_authorized(t)]
    if not unauthorized:
        return None
    msg = _format_refusal_for_unauthorized(unauthorized, scope)
    logging.warning("Engagement scope: refusing terminal command — %s", msg)
    return msg


def check_url_authorized(url_or_host: str) -> Optional[str]:
    """Check whether a single URL / host / host:port falls inside the active
    engagement scope.

    Used by URL-typed tool dispatch (``tools/web_tools.py``,
    ``tools/browser_tool.py``). Same return contract as
    :func:`check_command_authorized` — ``None`` for "allowed", else the
    refusal message. ``None`` is also returned when the input is empty
    or non-string (the caller's own validation will handle that).
    """
    if not url_or_host or not isinstance(url_or_host, str):
        return None
    scope = get_active_scope()
    if scope is None or scope.bypassed:
        return None
    if scope.is_target_authorized(url_or_host):
        return None
    msg = _format_refusal_for_unauthorized([url_or_host], scope)
    logging.warning("Engagement scope: refusing URL dispatch — %s", msg)
    return msg


def get_active_scope() -> Optional[EngagementScope]:
    """Return the EngagementScope active for the current process, or None.

    Populated by :func:`assert_active_scope` on each turn. Tools (terminal,
    web, browser) use this to gate dispatch against the operator's
    declared scope without re-reading the YAML file every call.

    Returns ``None`` when called outside an engagement (no turn has run
    through :func:`assert_active_scope` yet). Callers should treat that
    as "no enforcement to apply" rather than as a refusal — the
    pre-flight check in ``AIAgent.run_conversation()`` already prevents
    a real engagement from starting without a scope.
    """
    return _active_scope


def assert_active_scope() -> EngagementScope:
    """Load + validate the active scope, or refuse the engagement.

    Honors the ``SCARLIGHT_NO_ENGAGEMENT=1`` bypass for internal use.
    Otherwise raises :class:`EngagementScopeError` with an actionable
    message if no valid scope is found.

    On success with a real scope, defaults the terminal backend to Docker
    (Kali) if the operator hasn't pinned one — see
    :func:`_enforce_sandboxed_terminal_default`.

    Side effect: stores the returned scope into the module-level
    :data:`_active_scope` so :func:`get_active_scope` (used by tool
    enforcement) can find it without re-reading the YAML.
    """
    global _active_scope

    if _bypass_active():
        _warn_bypass_once()
        scope = _bypass_scope()
        _active_scope = scope
        return scope

    scope = load_active_scope()
    if scope is None:
        raise EngagementScopeError(_refusal_message())
    _enforce_sandboxed_terminal_default(scope)
    _active_scope = scope
    return scope

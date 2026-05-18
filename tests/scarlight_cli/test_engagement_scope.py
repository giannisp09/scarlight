"""Tests for the engagement-scope authorization guard (fork-runbook Step 7).

Scarlight refuses to start a turn without a valid engagement.yaml. These
tests cover discovery, validation, and the internal-use bypass env var.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from scarlight_cli import engagement_scope
from scarlight_cli.engagement_scope import (
    EngagementScope,
    EngagementScopeError,
    _extract_host,
    _extract_network_targets_from_command,
    assert_active_scope,
    check_command_authorized,
    check_url_authorized,
    get_active_scope,
    load_active_scope,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _valid_scope_dict() -> dict:
    """Minimal-but-valid scope payload. Tests mutate copies of this."""
    return {
        "engagement_id": "test-engagement-001",
        "authorization_reference": "test fixture",
        "operator_acknowledgment": {
            "acknowledged": True,
            "operator": "test operator",
            "date": "2026-05-18",
        },
        "targets": ["localhost", "127.0.0.1"],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_bypass(monkeypatch):
    """Tests in this module exercise the guard directly. The session-level
    autouse fixture in tests/conftest.py sets SCARLIGHT_NO_ENGAGEMENT=1 so
    AIAgent.run_conversation tests don't all break; here we clear it so we
    can test the actual guard behavior. Also resets the warn-once flags,
    clears TERMINAL_ENV so the sandbox-default helper sees a clean slate,
    and resets the active-scope cache so get_active_scope() doesn't
    leak between tests."""
    monkeypatch.delenv("SCARLIGHT_NO_ENGAGEMENT", raising=False)
    monkeypatch.delenv("SCARLIGHT_ENGAGEMENT", raising=False)
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    monkeypatch.setattr(engagement_scope, "_bypass_warned", False)
    monkeypatch.setattr(engagement_scope, "_sandbox_default_logged", False)
    monkeypatch.setattr(engagement_scope, "_active_scope", None)


@pytest.fixture
def in_isolated_cwd(tmp_path, monkeypatch):
    """Run from a tempdir so ./engagement.yaml doesn't pick up real files."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


# ── Discovery ──────────────────────────────────────────────────────────────


class TestDiscovery:
    def test_no_file_anywhere_returns_none(self, in_isolated_cwd, tmp_path, monkeypatch):
        # tests/conftest.py points SCARLIGHT_HOME at a per-test tempdir
        # with no engagement.yaml; CWD is also clean.
        assert load_active_scope() is None

    def test_override_env_var_takes_precedence(
        self, in_isolated_cwd, tmp_path, monkeypatch
    ):
        # Create three files, all with different engagement_ids; the env
        # var should win.
        override_path = tmp_path / "override.yaml"
        _write(override_path, {**_valid_scope_dict(), "engagement_id": "from-override"})
        _write(in_isolated_cwd / "engagement.yaml", {**_valid_scope_dict(), "engagement_id": "from-cwd"})
        home = Path(os.environ["SCARLIGHT_HOME"])
        _write(home / "engagement.yaml", {**_valid_scope_dict(), "engagement_id": "from-home"})

        monkeypatch.setenv("SCARLIGHT_ENGAGEMENT", str(override_path))
        scope = load_active_scope()
        assert scope is not None
        assert scope.engagement_id == "from-override"

    def test_cwd_engagement_yaml_used_when_no_override(self, in_isolated_cwd):
        _write(in_isolated_cwd / "engagement.yaml", {**_valid_scope_dict(), "engagement_id": "from-cwd"})
        home = Path(os.environ["SCARLIGHT_HOME"])
        _write(home / "engagement.yaml", {**_valid_scope_dict(), "engagement_id": "from-home"})

        scope = load_active_scope()
        assert scope is not None
        assert scope.engagement_id == "from-cwd"

    def test_scarlight_home_engagement_yaml_used_as_default(self, in_isolated_cwd):
        home = Path(os.environ["SCARLIGHT_HOME"])
        _write(home / "engagement.yaml", {**_valid_scope_dict(), "engagement_id": "from-home"})

        scope = load_active_scope()
        assert scope is not None
        assert scope.engagement_id == "from-home"

    def test_override_path_expanded(self, in_isolated_cwd, tmp_path, monkeypatch):
        # Ensure ``~`` in the env var is expanded.
        target = tmp_path / "x.yaml"
        _write(target, _valid_scope_dict())
        monkeypatch.setenv("SCARLIGHT_ENGAGEMENT", str(target))
        scope = load_active_scope()
        assert scope is not None


# ── Validation ────────────────────────────────────────────────────────────


class TestValidation:
    def test_valid_minimal(self, in_isolated_cwd):
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        scope = load_active_scope()
        assert isinstance(scope, EngagementScope)
        assert scope.engagement_id == "test-engagement-001"
        assert scope.operator == "test operator"
        assert scope.targets == ("localhost", "127.0.0.1")
        assert scope.bypassed is False
        assert scope.source_path is not None

    def test_invalid_yaml_raises(self, in_isolated_cwd):
        (in_isolated_cwd / "engagement.yaml").write_text(
            "engagement_id: 'unterminated", encoding="utf-8"
        )
        with pytest.raises(EngagementScopeError, match="not valid YAML"):
            load_active_scope()

    def test_empty_file_raises(self, in_isolated_cwd):
        (in_isolated_cwd / "engagement.yaml").write_text("", encoding="utf-8")
        with pytest.raises(EngagementScopeError, match="empty"):
            load_active_scope()

    def test_non_mapping_root_raises(self, in_isolated_cwd):
        (in_isolated_cwd / "engagement.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(EngagementScopeError, match="must be a YAML mapping"):
            load_active_scope()

    @pytest.mark.parametrize("missing_field", [
        "engagement_id",
        "authorization_reference",
    ])
    def test_missing_required_string_raises(self, in_isolated_cwd, missing_field):
        data = _valid_scope_dict()
        data.pop(missing_field)
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match=missing_field):
            load_active_scope()

    @pytest.mark.parametrize("empty_value", ["", "   "])
    def test_empty_required_string_raises(self, in_isolated_cwd, empty_value):
        data = _valid_scope_dict()
        data["engagement_id"] = empty_value
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="engagement_id"):
            load_active_scope()

    def test_missing_acknowledgment_block_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data.pop("operator_acknowledgment")
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="operator_acknowledgment"):
            load_active_scope()

    @pytest.mark.parametrize("bad_ack", [False, None, "true", 1, "yes"])
    def test_acknowledged_must_be_literal_true(self, in_isolated_cwd, bad_ack):
        data = _valid_scope_dict()
        data["operator_acknowledgment"]["acknowledged"] = bad_ack
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="must be literal"):
            load_active_scope()

    def test_missing_operator_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data["operator_acknowledgment"].pop("operator")
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="operator"):
            load_active_scope()

    def test_missing_date_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data["operator_acknowledgment"].pop("date")
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="date"):
            load_active_scope()

    def test_yaml_native_date_accepted(self, in_isolated_cwd):
        # YAML parses bare YYYY-MM-DD into a datetime.date object.
        (in_isolated_cwd / "engagement.yaml").write_text(
            "engagement_id: e\n"
            "authorization_reference: r\n"
            "operator_acknowledgment:\n"
            "  acknowledged: true\n"
            "  operator: o\n"
            "  date: 2026-05-18\n"
            "targets:\n"
            "  - localhost\n",
            encoding="utf-8",
        )
        scope = load_active_scope()
        assert scope is not None
        assert scope.acknowledged_at == "2026-05-18"

    @pytest.mark.parametrize("bad_targets", [None, [], "not-a-list", [""], ["valid", ""]])
    def test_targets_must_be_non_empty_list_of_non_empty_strings(
        self, in_isolated_cwd, bad_targets
    ):
        data = _valid_scope_dict()
        data["targets"] = bad_targets
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="targets"):
            load_active_scope()

    def test_expired_window_end_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        past = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        data["window"] = {"end": past}
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="window.end is in the past"):
            load_active_scope()

    def test_future_window_start_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        future = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
        data["window"] = {"start": future}
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="window.start is in the future"):
            load_active_scope()

    def test_window_open_now_passes(self, in_isolated_cwd):
        data = _valid_scope_dict()
        past = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
        data["window"] = {"start": past, "end": future}
        _write(in_isolated_cwd / "engagement.yaml", data)
        scope = load_active_scope()
        assert scope is not None
        assert scope.window_start is not None and scope.window_end is not None

    def test_window_z_suffix_accepted(self, in_isolated_cwd):
        data = _valid_scope_dict()
        # Hard-code a past start with the 'Z' UTC shorthand.
        data["window"] = {"start": "2020-01-01T00:00:00Z"}
        _write(in_isolated_cwd / "engagement.yaml", data)
        scope = load_active_scope()
        assert scope is not None
        assert scope.window_start == datetime(2020, 1, 1, tzinfo=timezone.utc)

    def test_invalid_iso8601_raises(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data["window"] = {"end": "not-a-date"}
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="ISO-8601"):
            load_active_scope()


# ── assert_active_scope ────────────────────────────────────────────────────


class TestAssertActiveScope:
    def test_raises_when_no_file(self, in_isolated_cwd):
        with pytest.raises(EngagementScopeError) as exc_info:
            assert_active_scope()
        msg = str(exc_info.value)
        assert "Refused to start engagement" in msg
        assert "engagement.yaml.example" in msg
        assert "CODE_OF_USE.md" in msg
        assert "SCARLIGHT_NO_ENGAGEMENT" in msg

    def test_returns_scope_when_valid(self, in_isolated_cwd):
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        scope = assert_active_scope()
        assert scope.engagement_id == "test-engagement-001"
        assert scope.bypassed is False

    def test_propagates_validation_error(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data.pop("engagement_id")
        _write(in_isolated_cwd / "engagement.yaml", data)
        with pytest.raises(EngagementScopeError, match="engagement_id"):
            assert_active_scope()

    @pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
    def test_bypass_env_var_truthy_values(self, in_isolated_cwd, monkeypatch, truthy):
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", truthy)
        scope = assert_active_scope()
        assert scope.bypassed is True
        assert scope.engagement_id == "bypass:no-engagement"
        assert scope.targets == ()

    @pytest.mark.parametrize("falsy", ["0", "false", "no", "off", ""])
    def test_bypass_env_var_falsy_values_do_not_bypass(
        self, in_isolated_cwd, monkeypatch, falsy
    ):
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", falsy)
        with pytest.raises(EngagementScopeError):
            assert_active_scope()

    def test_bypass_warning_logged_once_per_process(
        self, in_isolated_cwd, monkeypatch, caplog
    ):
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", "1")
        with caplog.at_level(logging.WARNING):
            assert_active_scope()
            assert_active_scope()
            assert_active_scope()
        bypass_warnings = [
            r for r in caplog.records
            if "Engagement authorization guard bypassed" in r.getMessage()
        ]
        assert len(bypass_warnings) == 1


# ── Sandboxed-terminal default (Step 5 + Step 7 coupling) ─────────────────


class TestSandboxedTerminalDefault:
    """A real engagement should force the terminal tool into the Kali
    sandbox unless the operator has pinned a backend explicitly.

    The hermes-agent inheritance complicates this: ``cli.load_cli_config()``
    runs at module import and bridges the schema default
    ``terminal.backend: local`` into ``TERMINAL_ENV=local`` before the
    engagement guard fires. So a bare ``TERMINAL_ENV=local`` looks identical
    to no setting at all. The override has to peek at config.yaml / .env
    to distinguish "operator pinned local" from "schema default leaked".
    """

    def test_real_scope_defaults_terminal_env_to_docker(self, in_isolated_cwd):
        # No env var, no config.yaml, no .env → must override to docker.
        assert "TERMINAL_ENV" not in os.environ
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        scope = assert_active_scope()
        assert not scope.bypassed
        assert os.environ.get("TERMINAL_ENV") == "docker"

    def test_schema_default_local_is_overridden(self, in_isolated_cwd, monkeypatch):
        # Mimic cli.load_cli_config()'s pre-emptive bridge: TERMINAL_ENV is
        # set to the schema default "local" before the guard fires, but
        # neither config.yaml nor .env actually pins it. Override.
        monkeypatch.setenv("TERMINAL_ENV", "local")
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        assert_active_scope()
        assert os.environ["TERMINAL_ENV"] == "docker"

    def test_explicit_non_local_terminal_env_is_preserved(
        self, in_isolated_cwd, monkeypatch
    ):
        # Any non-"local" value cannot be a schema-default leak; respect it.
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        assert_active_scope()
        assert os.environ["TERMINAL_ENV"] == "ssh"

    def test_config_yaml_pin_to_local_is_preserved(
        self, in_isolated_cwd, monkeypatch, tmp_path
    ):
        # Operator explicitly wrote terminal.backend: local in config.yaml.
        # Honor that — don't second-guess them just because we'd default
        # the other way.
        home = Path(os.environ["SCARLIGHT_HOME"])
        (home / "config.yaml").write_text(
            yaml.safe_dump({"terminal": {"backend": "local"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("TERMINAL_ENV", "local")  # what cli.py would set
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        assert_active_scope()
        assert os.environ["TERMINAL_ENV"] == "local"

    def test_dotenv_pin_is_preserved(self, in_isolated_cwd, monkeypatch):
        # Operator persisted via `scarlight config set terminal.backend
        # local` → ~/.scarlight/.env has the line. Honor it.
        home = Path(os.environ["SCARLIGHT_HOME"])
        (home / ".env").write_text("TERMINAL_ENV=local\n", encoding="utf-8")
        monkeypatch.setenv("TERMINAL_ENV", "local")  # mirrors .env loaded by dotenv
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        assert_active_scope()
        assert os.environ["TERMINAL_ENV"] == "local"

    def test_bypass_does_not_set_terminal_env(self, in_isolated_cwd, monkeypatch):
        # Internal harnesses and the test suite use bypass — we explicitly
        # don't want their terminal tool quietly switched to Docker.
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", "1")
        scope = assert_active_scope()
        assert scope.bypassed
        assert "TERMINAL_ENV" not in os.environ

    def test_sandbox_default_warning_logged_once_per_process(
        self, in_isolated_cwd, caplog
    ):
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        with caplog.at_level(logging.WARNING):
            assert_active_scope()
            # Second call would re-set TERMINAL_ENV (idempotent); the
            # warning, however, should fire exactly once per process so
            # the operator sees it but isn't spammed every turn.
            assert_active_scope()
            assert_active_scope()
        sandbox_warnings = [
            r for r in caplog.records
            if "defaulting TERMINAL_ENV=docker" in r.getMessage()
        ]
        assert len(sandbox_warnings) == 1


# ── Active-scope cache (get_active_scope) ──────────────────────────────────


class TestActiveScopeCache:
    """get_active_scope() returns whatever the last assert_active_scope()
    call populated, so tools can fetch the scope cheaply on every dispatch."""

    def test_returns_none_before_any_assert(self, in_isolated_cwd):
        assert get_active_scope() is None

    def test_populated_after_assert_with_real_scope(self, in_isolated_cwd):
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        scope = assert_active_scope()
        assert get_active_scope() is scope

    def test_populated_after_assert_with_bypass(self, in_isolated_cwd, monkeypatch):
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", "1")
        scope = assert_active_scope()
        cached = get_active_scope()
        assert cached is scope
        assert cached.bypassed is True


# ── Host extraction (_extract_host) ────────────────────────────────────────


class TestExtractHost:
    """Pluck canonical host from URL / host:port / bare host. Lowercases."""

    @pytest.mark.parametrize("value,expected", [
        ("acme.com", "acme.com"),
        ("Acme.Com", "acme.com"),
        ("https://acme.com/foo", "acme.com"),
        ("http://acme.com:8080/foo?q=1", "acme.com"),
        ("acme.com:443", "acme.com"),
        ("10.0.0.1", "10.0.0.1"),
        ("10.0.0.1:80", "10.0.0.1"),
        ("[::1]:8080", "::1"),
        ("::1", "::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("", ""),
        ("   ", ""),
    ])
    def test_extract_host_no_cidr(self, value, expected):
        assert _extract_host(value, allow_cidr=False) == expected

    def test_extract_host_with_cidr(self):
        assert _extract_host("10.0.0.0/24", allow_cidr=True) == "10.0.0.0/24"
        assert _extract_host("2001:db8::/32", allow_cidr=True) == "2001:db8::/32"

    def test_cidr_not_extracted_when_disabled(self):
        # With allow_cidr=False, a CIDR string isn't a valid host.
        assert _extract_host("10.0.0.0/24", allow_cidr=False) == ""

    def test_invalid_url_returns_empty(self):
        assert _extract_host("://broken", allow_cidr=False) == ""

    def test_non_string_returns_empty(self):
        assert _extract_host(None, allow_cidr=False) == ""  # type: ignore[arg-type]
        assert _extract_host(42, allow_cidr=False) == ""  # type: ignore[arg-type]


# ── Command-target extraction (_extract_network_targets_from_command) ──────


class TestExtractNetworkTargets:
    """Pull URLs, FQDNs, and IPs out of a shell command string."""

    def test_curl_url(self):
        targets = _extract_network_targets_from_command(
            "curl -si http://host.docker.internal:3000/robots.txt"
        )
        assert "http://host.docker.internal:3000/robots.txt" in targets
        assert "host.docker.internal" in targets

    def test_bare_hostname(self):
        targets = _extract_network_targets_from_command("nmap -sV example.com -p 80")
        assert "example.com" in targets

    def test_bare_ipv4(self):
        targets = _extract_network_targets_from_command("nc -v 10.0.0.5 8080")
        assert "10.0.0.5" in targets

    def test_bare_ipv6(self):
        targets = _extract_network_targets_from_command("ping6 2001:db8::1")
        assert "2001:db8::1" in targets

    def test_mixed_command(self):
        targets = _extract_network_targets_from_command(
            "curl https://a.com && nmap 10.0.0.1 && ssh user@b.example.org"
        )
        assert "https://a.com" in targets
        assert "a.com" in targets
        assert "10.0.0.1" in targets
        assert "b.example.org" in targets

    def test_empty_command_returns_empty_list(self):
        assert _extract_network_targets_from_command("") == []
        assert _extract_network_targets_from_command(None) == []  # type: ignore[arg-type]

    def test_command_with_no_network_targets(self):
        targets = _extract_network_targets_from_command(
            "apt-get update && apt-get install -y curl"
        )
        # 'apt-get' has no dots, no IP shape. 'curl' is a bare word.
        # The FQDN regex needs a TLD-shaped suffix.
        assert targets == []

    def test_deduplication(self):
        # Same hostname appearing multiple times should appear once.
        targets = _extract_network_targets_from_command(
            "curl example.com; curl example.com; curl example.com"
        )
        assert targets.count("example.com") == 1


# ── is_target_authorized (the core enforcement check) ──────────────────────


class TestIsTargetAuthorized:
    """The operator's targets list now enforces per-tool-call."""

    def _scope(self, *targets: str, bypassed: bool = False) -> EngagementScope:
        return EngagementScope(
            engagement_id="test",
            authorization_reference="test",
            operator="op",
            acknowledged_at="2026-05-18",
            targets=tuple(targets),
            bypassed=bypassed,
        )

    def test_exact_hostname_match(self):
        scope = self._scope("acme.com")
        assert scope.is_target_authorized("acme.com")

    def test_case_insensitive(self):
        scope = self._scope("Acme.Com")
        assert scope.is_target_authorized("acme.com")
        assert scope.is_target_authorized("ACME.COM")

    def test_url_matches_hostname_rule(self):
        scope = self._scope("acme.com")
        assert scope.is_target_authorized("https://acme.com/foo?q=1")
        assert scope.is_target_authorized("http://acme.com:8080/")

    def test_host_port_matches_hostname_rule(self):
        # Port-agnostic at the host level.
        scope = self._scope("acme.com")
        assert scope.is_target_authorized("acme.com:443")

    def test_substring_does_not_match(self):
        # "evil-acme.com" must NOT match "acme.com" (no substring matching).
        scope = self._scope("acme.com")
        assert not scope.is_target_authorized("evil-acme.com")
        assert not scope.is_target_authorized("acme.com.evil.net")

    def test_subdomain_does_not_match(self):
        # No implicit wildcards; subdomains need explicit listing.
        scope = self._scope("acme.com")
        assert not scope.is_target_authorized("api.acme.com")
        assert not scope.is_target_authorized("sub.acme.com")

    def test_subdomain_matches_when_explicitly_listed(self):
        scope = self._scope("acme.com", "api.acme.com")
        assert scope.is_target_authorized("api.acme.com")
        assert scope.is_target_authorized("acme.com")
        assert not scope.is_target_authorized("admin.acme.com")

    def test_ipv4_exact_match(self):
        scope = self._scope("10.0.0.5")
        assert scope.is_target_authorized("10.0.0.5")
        assert scope.is_target_authorized("http://10.0.0.5:8080/")
        assert not scope.is_target_authorized("10.0.0.6")

    def test_ipv4_cidr_match(self):
        scope = self._scope("10.0.0.0/24")
        assert scope.is_target_authorized("10.0.0.1")
        assert scope.is_target_authorized("10.0.0.254")
        assert scope.is_target_authorized("http://10.0.0.42:80/")
        assert not scope.is_target_authorized("10.0.1.1")  # outside /24

    def test_ipv4_cidr_does_not_match_hostnames(self):
        # CIDR rules can't match a hostname (no DNS resolution at this layer).
        scope = self._scope("10.0.0.0/24")
        assert not scope.is_target_authorized("acme.com")

    def test_ipv6_cidr_match(self):
        scope = self._scope("2001:db8::/32")
        assert scope.is_target_authorized("2001:db8::1")
        assert scope.is_target_authorized("[2001:db8::cafe]:8080")
        assert not scope.is_target_authorized("2001:db9::1")

    def test_bypassed_scope_authorizes_everything(self):
        # Internal harnesses / tests use bypass — they shouldn't see refusals.
        scope = self._scope("acme.com", bypassed=True)
        assert scope.is_target_authorized("anything.example.org")
        assert scope.is_target_authorized("10.0.0.1")

    def test_empty_input_refused(self):
        scope = self._scope("acme.com")
        assert not scope.is_target_authorized("")
        assert not scope.is_target_authorized("   ")

    def test_empty_targets_refuses_everything(self):
        # Validation rejects empty targets at load time, but defensively
        # test the method itself.
        scope = self._scope()
        assert not scope.is_target_authorized("acme.com")

    def test_demo_scope_authorizes_lab_target(self):
        # Mirrors demo/engagement.yaml's targets list.
        scope = self._scope(
            "host.docker.internal",
            "host.docker.internal:3000",
            "http://host.docker.internal:3000",
            "127.0.0.1",
            "localhost",
        )
        assert scope.is_target_authorized("http://host.docker.internal:3000/robots.txt")
        assert scope.is_target_authorized("127.0.0.1")
        assert scope.is_target_authorized("localhost")
        assert not scope.is_target_authorized("example.org")


# ── Public tool-side helpers: check_command_authorized / check_url_authorized ─


class TestCheckCommandAuthorized:
    """Verifies the helper terminal_tool calls before executing a command."""

    def _activate(self, *targets: str) -> EngagementScope:
        scope = EngagementScope(
            engagement_id="test", authorization_reference="t",
            operator="op", acknowledged_at="2026-05-18",
            targets=tuple(targets),
        )
        engagement_scope._active_scope = scope
        return scope

    def test_returns_none_when_no_active_scope(self):
        # No engagement loaded → no enforcement, no refusal.
        engagement_scope._active_scope = None
        assert check_command_authorized("curl http://evil.com/") is None

    def test_returns_none_when_scope_bypassed(self):
        engagement_scope._active_scope = EngagementScope(
            engagement_id="x", authorization_reference="x", operator="x",
            acknowledged_at="x", targets=(), bypassed=True,
        )
        assert check_command_authorized("curl http://evil.com/") is None

    def test_returns_none_for_command_without_network_targets(self):
        self._activate("acme.com")
        assert check_command_authorized("apt-get install -y curl") is None
        assert check_command_authorized("ls -la /tmp") is None

    def test_returns_none_when_all_targets_authorized(self):
        self._activate("acme.com", "10.0.0.0/24")
        assert check_command_authorized("curl https://acme.com/foo") is None
        assert check_command_authorized("nmap 10.0.0.5") is None
        assert check_command_authorized(
            "curl https://acme.com/ && nmap 10.0.0.99"
        ) is None

    def test_returns_refusal_for_unauthorized_target(self):
        self._activate("acme.com")
        msg = check_command_authorized("curl https://evil.com/")
        assert msg is not None
        assert "evil.com" in msg
        assert "acme.com" in msg  # the authorized list is named in the msg
        assert "Refused" in msg

    def test_refusal_lists_only_the_unauthorized_targets(self):
        self._activate("acme.com")
        msg = check_command_authorized(
            "curl https://acme.com/ && curl https://evil.com/"
        )
        assert msg is not None
        assert "evil.com" in msg


class TestCheckUrlAuthorized:
    """Verifies the helper web/browser tools call on URL-typed args."""

    def _activate(self, *targets: str) -> EngagementScope:
        scope = EngagementScope(
            engagement_id="test", authorization_reference="t",
            operator="op", acknowledged_at="2026-05-18",
            targets=tuple(targets),
        )
        engagement_scope._active_scope = scope
        return scope

    def test_authorized_url_returns_none(self):
        self._activate("acme.com")
        assert check_url_authorized("https://acme.com/foo") is None
        assert check_url_authorized("acme.com") is None

    def test_unauthorized_url_returns_refusal(self):
        self._activate("acme.com")
        msg = check_url_authorized("https://evil.com/")
        assert msg is not None
        assert "Refused" in msg

    def test_no_active_scope_returns_none(self):
        engagement_scope._active_scope = None
        assert check_url_authorized("https://anywhere.example/") is None

    def test_bypass_returns_none(self):
        engagement_scope._active_scope = EngagementScope(
            engagement_id="x", authorization_reference="x", operator="x",
            acknowledged_at="x", targets=(), bypassed=True,
        )
        assert check_url_authorized("https://anywhere.example/") is None

    def test_empty_input_returns_none(self):
        self._activate("acme.com")
        assert check_url_authorized("") is None
        assert check_url_authorized(None) is None  # type: ignore[arg-type]


# ── EngagementScope summary ────────────────────────────────────────────────


class TestSummaryLine:
    def test_summary_for_real_scope(self, in_isolated_cwd):
        _write(in_isolated_cwd / "engagement.yaml", _valid_scope_dict())
        scope = load_active_scope()
        assert scope is not None
        summary = scope.summary_line()
        assert "test-engagement-001" in summary
        assert "2 targets" in summary
        assert "test fixture" in summary

    def test_summary_for_singular_target(self, in_isolated_cwd):
        data = _valid_scope_dict()
        data["targets"] = ["only-one"]
        _write(in_isolated_cwd / "engagement.yaml", data)
        scope = load_active_scope()
        assert scope is not None
        assert "1 target" in scope.summary_line()
        assert "1 targets" not in scope.summary_line()

    def test_summary_for_bypass(self, in_isolated_cwd, monkeypatch):
        monkeypatch.setenv("SCARLIGHT_NO_ENGAGEMENT", "1")
        scope = assert_active_scope()
        assert "bypassed" in scope.summary_line()

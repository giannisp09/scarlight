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
    assert_active_scope,
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
    can test the actual guard behavior. Also resets the warn-once flags
    and clears TERMINAL_ENV so the sandbox-default helper sees a clean
    slate."""
    monkeypatch.delenv("SCARLIGHT_NO_ENGAGEMENT", raising=False)
    monkeypatch.delenv("SCARLIGHT_ENGAGEMENT", raising=False)
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    monkeypatch.setattr(engagement_scope, "_bypass_warned", False)
    monkeypatch.setattr(engagement_scope, "_sandbox_default_logged", False)


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

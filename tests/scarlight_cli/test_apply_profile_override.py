"""Regression tests for _apply_profile_override SCARLIGHT_HOME guard (issue #22502).

When SCARLIGHT_HOME is set to the scarlight root (e.g. systemd hardcodes
SCARLIGHT_HOME=/root/.scarlight), _apply_profile_override must still read
active_profile and update SCARLIGHT_HOME to the profile directory.

When SCARLIGHT_HOME is already a profile directory (.../profiles/<name>),
_apply_profile_override must trust it and return without re-reading
active_profile (child-process inheritance contract).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _run_apply_profile_override(
    tmp_path, monkeypatch, *, scarlight_home: str | None, active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.

    Returns the value of os.environ["SCARLIGHT_HOME"] after the call,
    or None if unset.
    """
    scarlight_root = tmp_path / ".scarlight"
    scarlight_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (scarlight_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (scarlight_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if scarlight_home is not None:
        monkeypatch.setenv("SCARLIGHT_HOME", scarlight_home)
    else:
        monkeypatch.delenv("SCARLIGHT_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["scarlight", "gateway", "start"])

    from scarlight_cli.main import _apply_profile_override
    _apply_profile_override()

    return os.environ.get("SCARLIGHT_HOME")


class TestApplyProfileOverrideScarlightHomeGuard:
    """Regression guard for issue #22502.

    Verifies that SCARLIGHT_HOME pointing to the scarlight root does NOT suppress
    the active_profile check, while SCARLIGHT_HOME already pointing to a
    profile directory IS trusted as-is.
    """

    def test_scarlight_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """SCARLIGHT_HOME=/root/.scarlight + active_profile=coder must redirect
        SCARLIGHT_HOME to .../profiles/coder.

        Bug scenario from #22502: systemd sets SCARLIGHT_HOME to the scarlight root
        and the user switches to a profile via `scarlight profile use`.
        Before the fix, the guard returned early and active_profile was ignored.
        """
        scarlight_root = tmp_path / ".scarlight"
        scarlight_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            scarlight_home=str(scarlight_root),
            active_profile="coder",
        )

        assert result is not None, "SCARLIGHT_HOME must be set after profile redirect"
        assert "profiles" in result, (
            f"Expected SCARLIGHT_HOME to point into profiles/ dir, got: {result!r}"
        )
        assert result.endswith("coder"), (
            f"Expected SCARLIGHT_HOME to end with 'coder', got: {result!r}"
        )

    def test_scarlight_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """SCARLIGHT_HOME=.../profiles/coder must not be overridden even when
        active_profile says something different.

        Preserves the child-process inheritance contract: a subprocess spawned
        with SCARLIGHT_HOME already set to a specific profile must stay in that
        profile.
        """
        scarlight_root = tmp_path / ".scarlight"
        profile_dir = scarlight_root / "profiles" / "coder"
        profile_dir.mkdir(parents=True, exist_ok=True)

        (scarlight_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("SCARLIGHT_HOME", str(profile_dir))
        monkeypatch.setattr(sys, "argv", ["scarlight", "gateway", "start"])

        from scarlight_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("SCARLIGHT_HOME") == str(profile_dir), (
            "SCARLIGHT_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_scarlight_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: SCARLIGHT_HOME unset + active_profile=coder must set
        SCARLIGHT_HOME to the profile directory (existing behaviour must not regress).
        """
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            scarlight_home=None,
            active_profile="coder",
        )

        assert result is not None
        assert "coder" in result

    def test_scarlight_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect SCARLIGHT_HOME."""
        scarlight_root = tmp_path / ".scarlight"
        scarlight_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("SCARLIGHT_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", ["scarlight", "gateway", "start"])
        (scarlight_root / "active_profile").write_text("default")

        from scarlight_cli.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("SCARLIGHT_HOME") is None

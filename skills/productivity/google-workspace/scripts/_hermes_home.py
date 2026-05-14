"""Resolve SCARLIGHT_HOME for standalone skill scripts.

Skill scripts may run outside the Hermes process (e.g. system Python,
nix env, CI) where ``scarlight_constants`` is not importable.  This module
provides the same ``get_scarlight_home()`` and ``display_scarlight_home()``
contracts as ``scarlight_constants`` without requiring it on ``sys.path``.

When ``scarlight_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``scarlight_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``SCARLIGHT_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from scarlight_constants import display_scarlight_home as display_scarlight_home
    from scarlight_constants import get_scarlight_home as get_scarlight_home
except (ModuleNotFoundError, ImportError):

    def get_scarlight_home() -> Path:
        """Return the Hermes home directory (default: ~/.scarlight).

        Mirrors ``scarlight_constants.get_scarlight_home()``."""
        val = os.environ.get("SCARLIGHT_HOME", "").strip()
        return Path(val) if val else Path.home() / ".scarlight"

    def display_scarlight_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``scarlight_constants.display_scarlight_home()``."""
        home = get_scarlight_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)

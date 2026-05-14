"""Shared helpers for direct xAI HTTP integrations."""

from __future__ import annotations


def scarlight_xai_user_agent() -> str:
    """Return a stable Scarlight-specific User-Agent for xAI HTTP calls."""
    try:
        from scarlight_cli import __version__
    except Exception:
        __version__ = "unknown"
    return f"Scarlight-Agent/{__version__}"

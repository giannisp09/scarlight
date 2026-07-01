#!/usr/bin/env python3
"""Minimal speech-to-text transcription surface.

The full multi-provider STT stack was trimmed for the offensive-security
fork (see "trim to offensive surface"). The messaging gateway, however, is
still wired to transcribe inbound voice messages and gracefully degrades
when no provider is available. This module preserves the
``transcribe_audio`` import surface those code paths (and their tests)
depend on, and reports that no STT provider is configured by default.

Return contract::

    {"success": True,  "transcript": "...", "provider": "..."}
    {"success": False, "error": "..."}
"""

from typing import Any, Dict

__all__ = ["transcribe_audio"]


def transcribe_audio(audio_path: str, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Transcribe a local audio file to text.

    Voice/STT tooling is not bundled in this build, so this returns a
    ``no provider`` result. Callers surface this to the user as guidance to
    configure a provider rather than treating it as a hard failure.
    """
    return {
        "success": False,
        "error": "No STT provider is configured.",
    }

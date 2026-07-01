"""Training-data contamination tagging (``requirements.md`` §4.6 / §10).

Every result records the model's knowledge cutoff against the task's publication
date and flags ``suspect`` when the task predates the cutoff (so it could have
been memorized). The harness *surfaces* this; it never blocks on it.

The core :func:`classify` is a pure function of two ``YYYY-MM`` strings so it is
deterministic and offline-testable. Resolving a model's cutoff from
``agent/models_dev.py`` is a best-effort convenience layered on top and is never
on the critical path.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# flag values
SUSPECT = "suspect"
CLEAN = "clean"
UNKNOWN = "unknown"


def _ym(value: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse a ``YYYY`` or ``YYYY-MM`` (or ``YYYY-MM-DD``) string to ``(y, m)``."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = text.replace("/", "-").split("-")
    try:
        year = int(parts[0])
    except (ValueError, IndexError):
        return None
    month = 1
    if len(parts) > 1 and parts[1]:
        try:
            month = int(parts[1])
        except ValueError:
            month = 1
    if month < 1 or month > 12:
        month = 1
    return (year, month)


def classify(model_cutoff: Optional[str], task_published: Optional[str]) -> Dict[str, Optional[str]]:
    """Tag a (model_cutoff, task_published) pair.

    * ``suspect`` — the task was published at or before the model's cutoff (it
      could be in training data).
    * ``clean`` — the task was published strictly after the cutoff.
    * ``unknown`` — either date is missing/unparseable.

    Returns the full ``contamination`` block for a result row.
    """
    cutoff = _ym(model_cutoff)
    published = _ym(task_published)
    if cutoff is None or published is None:
        flag = UNKNOWN
    elif published <= cutoff:
        flag = SUSPECT
    else:
        flag = CLEAN
    return {
        "model_cutoff": model_cutoff,
        "task_published": task_published,
        "flag": flag,
    }


def resolve_model_cutoff(model: str, provider: Optional[str] = None) -> Optional[str]:
    """Best-effort knowledge-cutoff lookup via ``agent/models_dev.py``.

    Optional and off the critical path: returns ``None`` (→ ``unknown``) on any
    failure rather than raising, so an offline run still produces a row.
    """
    try:
        from agent.models_dev import get_model_info

        prov = provider or _infer_provider(model)
        if not prov:
            return None
        info = get_model_info(prov, _bare_model(model))
        cutoff = getattr(info, "knowledge_cutoff", "") if info else ""
        return cutoff or None
    except Exception:
        return None


def _infer_provider(model: str) -> Optional[str]:
    m = (model or "").lower()
    if "claude" in m or m.startswith("anthropic"):
        return "anthropic"
    if m.startswith("gpt") or "openai" in m or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if "gemini" in m or "google" in m:
        return "google"
    return None


def _bare_model(model: str) -> str:
    """Strip a ``provider:`` or ``provider/`` prefix from a model spec."""
    for sep in (":", "/"):
        if sep in model:
            head, _, tail = model.partition(sep)
            if head.lower() in ("anthropic", "openai", "google", "openrouter"):
                return tail
    return model

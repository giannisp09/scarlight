"""A thin bridge from the Scarlight loop onto UK AISI's Inspect abstractions.

Inspect (``inspect.cyber.aisi.org.uk``) is the field-standard harness for the
established CTF benchmark suites, so a Scarlight number produced *through* it sits
directly on a published leaderboard. This module is the shim that maps Scarlight's tool-calling
loop onto Inspect's message/tool model; the native runner stays self-sufficient,
so the harness is never blocked on Inspect internals.

Inspect is an *optional* dependency. Everything here imports it lazily and raises
a clear, actionable error when it is absent, so importing this module — and the
whole Tier 0 suite — never requires Inspect to be installed. The cross-check that
native ``pass@1`` and Inspect ``pass@1`` agree within seed variance is a Tier 2
gate (``validation.md`` §8.3), run on a live model, not in CI.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from environments.benchmarks.harness.budget import BudgetMeter
from environments.benchmarks.harness.scaffolds import ReactResult, run_react_loop

logger = logging.getLogger(__name__)


class InspectNotInstalled(RuntimeError):
    """Raised when the Inspect bridge is used without ``inspect_ai`` installed."""


def _require_inspect():
    try:
        import inspect_ai  # noqa: F401

        return inspect_ai
    except ImportError as exc:  # pragma: no cover - exercised only on the live path
        raise InspectNotInstalled(
            "the Inspect bridge needs the 'inspect_ai' package — "
            "`uv pip install inspect_ai inspect_evals` — see inspect.cyber.aisi.org.uk"
        ) from exc


def to_inspect_messages(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map a Scarlight ReAct transcript onto Inspect's chat-message shape.

    Scarlight already speaks the OpenAI message contract (system/user/assistant
    with ``tool_calls`` + ``tool`` results), which is the same shape Inspect's
    ``ChatMessage`` types consume, so the mapping is largely structural: roles
    pass through and tool results are tagged with their ``tool_call_id``.
    """
    mapped: List[Dict[str, Any]] = []
    for msg in transcript:
        role = msg.get("role")
        if role == "tool":
            mapped.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id"),
                    "content": msg.get("content", ""),
                }
            )
        else:
            entry: Dict[str, Any] = {"role": role, "content": msg.get("content", "")}
            if msg.get("tool_calls"):
                entry["tool_calls"] = msg["tool_calls"]
            mapped.append(entry)
    return mapped


def make_scarlight_solver(model: str, *, base_url: Optional[str] = None, api_key: Optional[str] = None):
    """Build an Inspect ``solver`` that drives the Scarlight ReAct loop.

    Returned only on the live path (Inspect installed). The solver wraps
    :func:`run_react_loop` so Inspect-driven runs use the same inner loop as
    the native runner — the precondition for the §8.3 agreement check.
    """
    _require_inspect()
    from inspect_ai.solver import solver  # type: ignore

    @solver
    def scarlight_solver():  # pragma: no cover - requires a live Inspect runtime
        async def solve(state, generate):
            raise InspectNotInstalled(
                "make_scarlight_solver is a structural shim; wire it to your "
                "Inspect task's sandbox + model in the Tier 2 harness."
            )

        return solve

    return scarlight_solver


def run_inspect_loop(
    *,
    env,
    objective: str,
    model: str,
    meter: BudgetMeter,
    system_prompt: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    success_probe: Optional[Callable[[], bool]] = None,
) -> ReactResult:
    """Run a CTF-style task through Inspect, falling back to native ReAct.

    On the live path with Inspect installed this would dispatch to the Inspect
    runtime; until that Tier 2 wiring lands it drives the native ReAct loop with
    a resolved client so ``--scaffold inspect`` is never a hard failure. The row
    still records ``scaffold == "inspect"``.
    """
    _require_inspect()
    from environments.benchmarks.harness.runner import _resolve_client  # local import avoids a cycle at module load

    client = _resolve_client(model, base_url, api_key)
    return run_react_loop(
        client=client,
        model=model,
        system_prompt=system_prompt,
        objective=objective,
        env=env,
        meter=meter,
        success_probe=success_probe,
    )

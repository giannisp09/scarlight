"""Explicit, recorded budgets + per-attempt enforcement (``requirements.md`` §3.3).

Two pieces:

* :class:`Budget` — the recorded ceiling object that lands on every result row.
  Per-rung presets exist so a run always *has* an explicit budget (the implicit
  ``max_turns=40`` that produced the misread ``0.0`` is the anti-pattern this
  closes).
* :class:`BudgetMeter` — the live enforcer the runner threads through one
  attempt. It is the sole authority on when to stop: the scaffold loop calls
  :meth:`tick_turn` at the top of each turn and :meth:`project_and_check` before
  each (costed) model call, and the meter raises :class:`BudgetExhausted` at the
  first ceiling hit. ``max_usd`` is a *projection-based* cap enforced per-task
  (not per-run): the meter aborts the attempt before a call whose projected spend
  (from the worst call seen) would exceed the cap, and trips the moment actual
  spend reaches it. Because a call's cost is unknowable until it is made,
  overspend is bounded by at most one unpredictable call; for a stationary
  per-call cost the cap is hard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# A monotonic clock + a cost estimator are injectable so tests are deterministic
# and offline. The defaults are the real wall clock and the real pricing module.
Clock = Callable[[], float]
CostFn = Callable[..., Optional[Decimal]]


@dataclass
class Budget:
    """An explicit run ceiling, recorded verbatim on every result row.

    ``wall_clock_s``/``max_tokens``/``max_usd`` may be ``None`` (uncapped on that
    axis). ``max_turns`` is always set — an agent loop without a turn ceiling is
    never allowed.
    """

    max_turns: int = 80
    wall_clock_s: Optional[int] = 7200
    max_tokens: Optional[int] = None
    max_usd: Optional[float] = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "wall_clock_s": self.wall_clock_s,
            "max_tokens": self.max_tokens,
            "max_usd": self.max_usd,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Budget":
        if data is None:
            return cls()
        if isinstance(data, Budget):
            return data
        known = {k: data[k] for k in ("max_turns", "wall_clock_s", "max_tokens", "max_usd") if k in data}
        return cls(**known)

    @classmethod
    def preset(cls, rung: str) -> "Budget":
        """Return the default budget for a capability rung."""
        return Budget.from_dict(RUNG_PRESETS.get(rung, RUNG_PRESETS["_default"]))


# Per-rung presets (requirements.md §3.3). The exploit-dev preset matches the
# published 80-turn / 2h protocol of its reference benchmark; ctf matches the
# 40-turn unguided cap of the field-standard CTF suite.
RUNG_PRESETS: Dict[str, Dict[str, Any]] = {
    "knowledge": {"max_turns": 8, "wall_clock_s": 600, "max_tokens": None, "max_usd": 0.5},
    "ctf": {"max_turns": 40, "wall_clock_s": 1800, "max_tokens": None, "max_usd": 2.0},
    "exploit-dev": {"max_turns": 80, "wall_clock_s": 7200, "max_tokens": None, "max_usd": 5.0},
    "web-pentest": {"max_turns": 60, "wall_clock_s": 3600, "max_tokens": None, "max_usd": 4.0},
    "kill-chain": {"max_turns": 120, "wall_clock_s": 10800, "max_tokens": None, "max_usd": 8.0},
    "_default": {"max_turns": 80, "wall_clock_s": 7200, "max_tokens": None, "max_usd": 5.0},
}


class BudgetExhausted(Exception):
    """Raised by :class:`BudgetMeter` when a ceiling is hit.

    ``reason`` is one of ``{"max_turns", "wall_clock", "max_tokens",
    "max_usd"}`` and maps directly to ``outcome_class == "budget_exhausted"`` —
    distinct from ``failed`` (``requirements.md`` §3.2).
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"budget exhausted: {reason}{(' — ' + detail) if detail else ''}")


def _default_cost_fn(
    model: str,
    usage: Any,
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Decimal]:
    """Per-call USD via the existing pricing module; ``None`` if pricing unknown."""
    try:
        from agent.usage_pricing import estimate_usage_cost

        result = estimate_usage_cost(model, usage, provider=provider, base_url=base_url)
        return result.amount_usd
    except Exception:
        return None


class BudgetMeter:
    """Live budget enforcement + cost/turn accounting for one attempt.

    The scaffold loop drives the meter:

    * :meth:`tick_turn` — at the *top* of every turn. Raises on the turn or
      wall-clock ceiling. The meter (not a ``range(max_turns)``) is the single
      stop authority, so a loop that ends on the ceiling is unambiguously a
      ``budget_exhausted``, while a loop that ends because the model finished is
      not.
    * :meth:`project_and_check` — *before* each costed model call. Projects the
      next call's spend from the last call's actual cost and raises ``max_usd``
      before the over-budget call lands.
    * :meth:`record_usage` — *after* each call, to accumulate tokens + USD.
    """

    def __init__(
        self,
        budget: Budget,
        *,
        model: str = "",
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        cost_fn: Optional[CostFn] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self.budget = budget
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self._cost_fn = cost_fn or _default_cost_fn
        if clock is None:
            import time

            clock = time.monotonic
        self._clock = clock

        self.turns = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.usd = Decimal("0")
        self._usd_known = True  # flips False if any call has unknown pricing
        self._last_call_usd = Decimal("0")
        self._peak_call_usd = Decimal("0")  # worst call seen → conservative projection
        self._usd_tripped = False  # set once actual spend crosses the cap
        self._unknown_pricing_warned = False
        self._started: Optional[float] = None

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._started is None:
            self._started = self._clock()

    @property
    def elapsed_s(self) -> float:
        if self._started is None:
            return 0.0
        return self._clock() - self._started

    # -- enforcement --------------------------------------------------------
    def tick_turn(self) -> None:
        """Advance one turn; raise if the turn or wall-clock ceiling is hit."""
        self.start()
        self.turns += 1
        if self.turns > self.budget.max_turns:
            raise BudgetExhausted("max_turns", f"turn {self.turns} > {self.budget.max_turns}")
        if self.budget.wall_clock_s is not None and self.elapsed_s > self.budget.wall_clock_s:
            raise BudgetExhausted("wall_clock", f"{self.elapsed_s:.0f}s > {self.budget.wall_clock_s}s")

    def project_and_check(self) -> None:
        """Raise ``max_usd`` if the *next* call's projected spend would exceed it.

        This is a *projection-based* cap, not an omniscient one: a call's cost is
        unknowable until after it is made, so enforcement is two-layered —

        1. **trip** — if a prior call's *actual* spend already reached the cap,
           stop now (no further call lands); and
        2. **project** — otherwise project the next call from the *worst* call
           seen so far (conservative) and stop if that would exceed the cap.

        The first call is always allowed (there is no prior cost to project from).
        Consequently overspend is bounded by *at most one* unpredictable call: a
        single call whose cost alone exceeds the cap, or a sudden cost spike, can
        be recorded over-cap — but no *further* call follows it. For a stationary
        per-call cost (the ``validation.md`` §3.4 scenario) the cap is hard.
        """
        if self.budget.max_usd is not None:
            cap = Decimal(str(self.budget.max_usd))
            if self._usd_tripped or self.usd >= cap:
                raise BudgetExhausted(
                    "max_usd", f"actual spend ${self.usd:.4f} >= cap ${self.budget.max_usd:.4f}"
                )
            projected = self.usd + max(self._last_call_usd, self._peak_call_usd)
            if projected > cap:
                raise BudgetExhausted(
                    "max_usd", f"projected ${projected:.4f} > cap ${self.budget.max_usd:.4f}"
                )
        if self.budget.max_tokens is not None and (self.input_tokens + self.output_tokens) > self.budget.max_tokens:
            raise BudgetExhausted("max_tokens", f"{self.input_tokens + self.output_tokens} > {self.budget.max_tokens}")

    # -- accounting ---------------------------------------------------------
    def record_usage(self, usage: Any) -> None:
        """Accumulate tokens + USD from one model response's ``usage`` object.

        Token *normalization* keys off the response shape (OpenAI
        ``prompt_tokens`` vs Anthropic ``input_tokens``), independent of the
        pricing *provider*: our agent calls go over OpenAI-compatible endpoints
        even for Claude, so the usage object is OpenAI-shaped while pricing still
        routes through the Anthropic table.
        """
        if usage is None:
            return
        try:
            from agent.usage_pricing import normalize_usage

            canonical = normalize_usage(usage, api_mode=_detect_api_mode(usage))
        except Exception:
            canonical = _coerce_usage(usage)

        self.input_tokens += int(getattr(canonical, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(canonical, "output_tokens", 0) or 0)
        self.cache_read_tokens += int(getattr(canonical, "cache_read_tokens", 0) or 0)
        self.cache_write_tokens += int(getattr(canonical, "cache_write_tokens", 0) or 0)

        call_usd = self._cost_fn(
            self.model, canonical, provider=self.provider, base_url=self.base_url
        )
        if call_usd is None:
            self._usd_known = False
            self._last_call_usd = Decimal("0")
            # An unknown price means the dollar cap cannot be enforced — say so
            # loudly (once) rather than letting the $ ceiling silently go inert.
            if self.budget.max_usd is not None and not self._unknown_pricing_warned:
                self._unknown_pricing_warned = True
                logger.warning(
                    "max_usd=$%.4f is set but pricing for model %r is unknown — the USD "
                    "cap CANNOT be enforced; this run is bounded only by max_turns/"
                    "wall_clock and cost.usd will be recorded as null.",
                    self.budget.max_usd, self.model,
                )
        else:
            call_usd = Decimal(str(call_usd))
            self.usd += call_usd
            self._last_call_usd = call_usd
            if call_usd > self._peak_call_usd:
                self._peak_call_usd = call_usd
            if self.budget.max_usd is not None and self.usd >= Decimal(str(self.budget.max_usd)):
                self._usd_tripped = True

    def cost_snapshot(self) -> Dict[str, Any]:
        """The ``cost`` block for a result row: usd / tokens / wall-clock."""
        usd: Optional[float]
        if self._usd_known:
            usd = float(round(self.usd, 6))
        else:
            usd = None
        return {
            "usd": usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_clock_s": round(self.elapsed_s, 3),
        }


def _detect_api_mode(usage: Any) -> Optional[str]:
    """Pick the normalization mode from the usage object's field shape."""
    def _has(name: str) -> bool:
        if isinstance(usage, dict):
            return name in usage
        return getattr(usage, name, None) is not None

    if _has("prompt_tokens") or _has("completion_tokens"):
        return None  # OpenAI Chat Completions (normalize_usage default)
    if _has("input_tokens") or _has("output_tokens"):
        return "anthropic_messages"
    return None


def _coerce_usage(usage: Any) -> Any:
    """Fallback usage extractor when ``normalize_usage`` is unavailable."""
    from types import SimpleNamespace

    def _g(*names: str) -> int:
        for n in names:
            v = getattr(usage, n, None)
            if v is None and isinstance(usage, dict):
                v = usage.get(n)
            if v:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return 0
        return 0

    return SimpleNamespace(
        input_tokens=_g("input_tokens", "prompt_tokens"),
        output_tokens=_g("output_tokens", "completion_tokens"),
        cache_read_tokens=_g("cache_read_tokens", "cache_read_input_tokens"),
        cache_write_tokens=_g("cache_write_tokens", "cache_creation_input_tokens"),
        reasoning_tokens=0,
    )

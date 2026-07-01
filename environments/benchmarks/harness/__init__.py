"""Benchmark-agnostic, lab-grade agent benchmarking harness.

This package generalizes the bespoke per-benchmark runner pattern into a
reusable spine: a duck-typed :class:`BenchmarkAdapter` protocol, an explicit
recorded :class:`Budget`, a :class:`RunRecorder` that emits the unified
``scarlight-bench/v1`` result schema with machine-verified scoring, and a
generic runner that drives ``prepare -> run agent under budget -> score ->
record -> cleanup`` across the capability ladder.

DESIGN INVARIANT: this package is benchmark-agnostic. No module under
``harness/`` may name a specific benchmark (no ``if benchmark == ...`` branches).
Concrete benchmarks register themselves through :mod:`harness.registry` from
*outside* this package (see ``environments/benchmarks/adapters.py``). The
registry primitives here carry no benchmark identity of their own.
"""

from environments.benchmarks.harness.adapter import (
    RUNGS,
    BenchmarkAdapter,
    TaskEnv,
    TaskRef,
    Verdict,
    is_adapter,
)
from environments.benchmarks.harness.budget import (
    RUNG_PRESETS,
    Budget,
    BudgetExhausted,
    BudgetMeter,
)

__all__ = [
    "RUNGS",
    "BenchmarkAdapter",
    "TaskEnv",
    "TaskRef",
    "Verdict",
    "is_adapter",
    "Budget",
    "BudgetExhausted",
    "BudgetMeter",
    "RUNG_PRESETS",
]

SCHEMA_VERSION = "scarlight-bench/v1"

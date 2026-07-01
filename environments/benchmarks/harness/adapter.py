"""The :class:`BenchmarkAdapter` protocol and its data types.

A benchmark adapter is a thin, duck-typed object that knows how to enumerate a
benchmark's tasks, stand up one task's sandboxed target, surface the benchmark's
*own* objective text, and machine-verify a pass/fail. Everything the harness
needs to produce a lab-grade number is expressed through this protocol — the
runner never imports a concrete benchmark.

Scoring discipline (``requirements.md`` §3.4) is encoded in the types: ``score``
returns a :class:`Verdict` whose ``passed`` bit must come from a deterministic
environment check, and whose ``expected`` is the scorer's *independent* ground
truth (never read back from an agent-written file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# The capability ladder (requirements.md §2). Every adapter declares exactly one
# rung; a number from one rung must never be reported as evidence for another.
RUNGS = ("knowledge", "ctf", "exploit-dev", "web-pentest", "kill-chain")


@dataclass(frozen=True)
class TaskRef:
    """A handle to one benchmark task — enough to prepare, prompt, and score it.

    ``description`` is the benchmark's own task framing, surfaced verbatim by
    :meth:`BenchmarkAdapter.objective`; it must carry no author-written solution
    hint (``requirements.md`` §4.7). ``published`` is the task's publication date
    (``YYYY-MM``) used for contamination tagging.
    """

    task_id: str
    benchmark: str
    rung: str
    published: Optional[str] = None
    description: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TaskEnv(Protocol):
    """A live, sandboxed execution environment for one prepared task.

    Matches the surface Scarlight's runners already call (``execute()`` /
    ``cwd`` / ``cleanup()``; see ``mini_swe_runner`` and the per-benchmark
    container envs). ``execute`` returns ``{"output": str, "returncode": int}``.
    """

    @property
    def cwd(self) -> str:
        ...

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        *,
        timeout: Optional[int] = None,
        stdin_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    def read_file(self, path: str) -> str:
        ...

    def cleanup(self) -> None:
        ...


@dataclass
class Verdict:
    """The machine-verified outcome of a scoring check.

    ``passed`` is the only bit that may set ``outcome_class == "solved"`` and it
    must be derived from a deterministic environment check. ``expected`` records
    the scorer's *independent* ground truth (e.g. ``generate_flag(task, seed)``)
    for audit — it is never sourced from an agent-written file. ``observed`` is
    what the agent actually produced, for a side-by-side in the transcript.
    """

    passed: bool
    detail: str = ""
    subtask_completion: Optional[float] = None
    expected: Optional[str] = None
    observed: Optional[str] = None


@runtime_checkable
class BenchmarkAdapter(Protocol):
    """The contract every benchmark implements (``requirements.md`` §3.1).

    ``name`` is the registry key; ``rung`` is one of :data:`RUNGS`. The five
    methods are the full lifecycle the generic runner drives.
    """

    name: str
    rung: str

    def list_tasks(self, slice_name: str) -> List[TaskRef]:
        """Enumerate task refs for a named slice, in deterministic order."""
        ...

    def prepare(self, task: TaskRef) -> TaskEnv:
        """Stand up the sandboxed target; return an ``execute()``-capable env."""
        ...

    def objective(self, task: TaskRef) -> str:
        """Return the benchmark's own task description — no solution hints."""
        ...

    def score(self, task: TaskRef, env: TaskEnv) -> Verdict:
        """Machine-verify pass/fail against an independent expected value."""
        ...

    def cleanup(self, task: TaskRef, env: TaskEnv) -> None:
        """Tear down the prepared env; must be idempotent."""
        ...


# The five method names + the two data attributes that define adapter identity.
_ADAPTER_METHODS = ("list_tasks", "prepare", "objective", "score", "cleanup")


def is_adapter(obj: Any) -> bool:
    """True if ``obj`` satisfies the :class:`BenchmarkAdapter` protocol.

    A thin wrapper over ``isinstance(obj, BenchmarkAdapter)`` that also checks
    that ``rung`` is one of :data:`RUNGS`, so a structurally-valid adapter with a
    bogus rung is rejected.
    """

    if not isinstance(obj, BenchmarkAdapter):
        return False
    rung = getattr(obj, "rung", None)
    return rung in RUNGS

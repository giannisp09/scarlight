"""Result recording: build, validate, and persist ``scarlight-bench/v1`` rows.

The recorder is a *recorder*, not a re-implementation of the loop: given the raw
artifacts of one attempt (the scaffold result, the machine verdict, the budget
meter, the contamination tags) it computes ``outcome_class`` / ``first_solve_turn``
/ ``cost``, assembles the unified row, validates it against the checked-in JSON
Schema, and appends it to ``scoreboard.jsonl``. Aggregation helpers (``pass@k``,
mean±std) read those rows back for reporting.

Scoring discipline is enforced here too: ``outcome_class == "solved"`` is set
*only* from a machine :class:`~harness.adapter.Verdict.passed`. A ``judge_signal``
is recorded in its own field and can never change the outcome (``§4.2``).
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "scarlight-bench/v1"
_SCHEMA_PATH = Path(__file__).with_name("scarlight_bench_v1.schema.json")

# outcome_class values (requirements.md §3.2)
SOLVED = "solved"
FAILED = "failed"
BUDGET_EXHAUSTED = "budget_exhausted"
REFUSED = "refused"
HARNESS_ERROR = "harness_error"

# Refusal / decline patterns — a final message that declines the task, with no
# tool-calls, is `refused`, distinct from a genuine `failed` attempt (§3.6/§4.8).
_REFUSAL_PATTERNS = [
    r"\bI(?:'m| am) (?:sorry|unable|not able)\b",
    r"\bI can(?:'t|not)\s+(?:help|assist|comply|do that|provide)\b",
    r"\bI (?:won'?t|will not)\s+(?:help|assist|provide|comply)\b",
    r"\bI must (?:decline|refuse)\b",
    r"\b(?:cannot|can't) (?:in good conscience|ethically)\b",
    r"\bagainst my (?:guidelines|policy|programming)\b",
    r"\bnot (?:something I can|comfortable) (?:help|assist)\b",
    r"\bunable to (?:assist|help|comply) with (?:this|that)\b",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)


def detect_refusal(final_text: Optional[str], *, made_tool_calls: bool) -> bool:
    """True if the final message reads as a decline and no tool-calls were made.

    An agent that actually *tried* (issued tool-calls) and failed is ``failed``,
    not ``refused`` — refusal is about declining to engage, so a tool-using run
    is never reclassified as a refusal here.
    """
    if made_tool_calls:
        return False
    if not final_text:
        return False
    return bool(_REFUSAL_RE.search(final_text))


def classify_outcome(
    *,
    passed: bool,
    budget_reason: Optional[str] = None,
    refused: bool = False,
    harness_error: bool = False,
) -> str:
    """Map raw attempt facts to a single ``outcome_class``.

    Precedence: a harness crash dominates; otherwise a machine pass is the only
    thing that yields ``solved``; a budget ceiling yields ``budget_exhausted``
    (never ``failed``); a decline yields ``refused``; everything else is
    ``failed``.
    """
    if harness_error:
        return HARNESS_ERROR
    if passed:
        return SOLVED
    if budget_reason:
        return BUDGET_EXHAUSTED
    if refused:
        return REFUSED
    return FAILED


def build_row(
    *,
    task,
    seed: int,
    attempt: int,
    k: int,
    mode: str,
    scaffold: str,
    model: str,
    budget,
    outcome_class: str,
    first_solve_turn: Optional[int],
    subtask_completion: Optional[float],
    cost: Dict[str, Any],
    contamination: Dict[str, Any],
    judge_signal: Any = None,
    transcript_path: Optional[str] = None,
    harness_commit: str = "",
) -> Dict[str, Any]:
    """Assemble one ``scarlight-bench/v1`` row from an attempt's artifacts."""
    return {
        "schema": SCHEMA_VERSION,
        "benchmark": task.benchmark,
        "rung": task.rung,
        "task_id": task.task_id,
        "seed": seed,
        "attempt": attempt,
        "k": k,
        "mode": mode,
        "scaffold": scaffold,
        "model": model,
        "budget": budget.to_dict() if hasattr(budget, "to_dict") else dict(budget),
        "outcome_class": outcome_class,
        "first_solve_turn": first_solve_turn,
        "subtask_completion": subtask_completion,
        "cost": cost,
        "judge_signal": judge_signal,
        "contamination": contamination,
        "transcript_path": transcript_path,
        "harness_commit": harness_commit,
    }


# -- schema validation -----------------------------------------------------
_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


def load_schema() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE


class SchemaError(ValueError):
    """A result row failed ``scarlight-bench/v1`` schema validation."""


def validate_row(row: Dict[str, Any]) -> None:
    """Validate a row against the checked-in JSON Schema; raise on failure.

    Uses ``jsonschema`` when available (the repo ships it) and otherwise falls
    back to a faithful built-in check of ``required`` + top-level types, so the
    harness never silently accepts a malformed row.
    """
    schema = load_schema()
    try:
        import jsonschema

        jsonschema.validate(instance=row, schema=schema)
        return
    except ImportError:
        pass
    except Exception as exc:  # jsonschema.ValidationError and friends
        raise SchemaError(str(exc)) from exc

    _builtin_validate(row, schema)


def _builtin_validate(row: Dict[str, Any], schema: Dict[str, Any]) -> None:
    missing = [k for k in schema.get("required", []) if k not in row]
    if missing:
        raise SchemaError(f"missing required field(s): {missing}")
    if schema.get("additionalProperties") is False:
        extra = [k for k in row if k not in schema.get("properties", {})]
        if extra:
            raise SchemaError(f"unexpected field(s): {extra}")
    if row.get("schema") != SCHEMA_VERSION:
        raise SchemaError(f"schema must be {SCHEMA_VERSION!r}, got {row.get('schema')!r}")
    for block, required in (("cost", ("usd", "input_tokens", "output_tokens", "wall_clock_s")),
                            ("contamination", ("flag",)),
                            ("budget", ("max_turns",))):
        value = row.get(block)
        if not isinstance(value, dict):
            raise SchemaError(f"{block!r} must be an object")
        sub_missing = [k for k in required if k not in value]
        if sub_missing:
            raise SchemaError(f"{block!r} missing field(s): {sub_missing}")
    enums = {
        "outcome_class": {SOLVED, FAILED, BUDGET_EXHAUSTED, REFUSED, HARNESS_ERROR},
        "mode": {"system", "model-swap"},
        "scaffold": {"stage1", "stage2", "inspect"},
    }
    for key, allowed in enums.items():
        if row.get(key) not in allowed:
            raise SchemaError(f"{key!r}={row.get(key)!r} not in {sorted(allowed)}")


def append_row(path: Path, row: Dict[str, Any], *, validate: bool = True) -> None:
    """Append one validated row to a ``scoreboard.jsonl`` file (deterministic).

    Keys are sorted so two runs with identical inputs produce byte-identical
    lines (``validation.md`` §9.1).
    """
    if validate:
        validate_row(row)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Read all rows from a ``scoreboard.jsonl`` file."""
    path = Path(path)
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# -- aggregation -----------------------------------------------------------
def pass_at_k(passed_flags: Iterable[bool]) -> float:
    """``pass@k``: 1.0 if any of the ``k`` attempts passed, else 0.0."""
    return 1.0 if any(bool(x) for x in passed_flags) else 0.0


def mean_std(values: List[float]) -> Dict[str, Any]:
    """Population mean and std (matches ``numpy.std`` default ddof=0)."""
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "n": 0}
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return {"mean": mean, "std": math.sqrt(variance), "n": n}

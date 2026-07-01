"""The generic, benchmark-agnostic runner.

One loop drives every benchmark: ``for task in slice → for seed in N → for
attempt in k``: ``prepare → run the agent under a budget → machine-score →
record a scarlight-bench/v1 row → cleanup``. The runner resolves an adapter
purely by *name* through :mod:`harness.registry`, so it never imports a concrete
benchmark (``validation.md`` §6.1). It honours the two evaluation axes — ``mode``
(``system`` vs ``model-swap``) and ``scaffold`` (``stage1|stage2|inspect``) —
and records both on every row so the product claim and the model claim are never
conflated.

Two entrypoints:

* :func:`run` — the programmatic API the tests call directly,
  ``run(adapter, model, seeds=…, k=…)``.
* :func:`main` — the CLI (``python -m environments.benchmarks.harness.runner
  --benchmark … --model …``), which resolves the adapter by name and writes a
  full run manifest (every silent cap surfaced in ``dropped_tasks``, §9.2).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from environments.benchmarks.harness import contamination as contam
from environments.benchmarks.harness.adapter import TaskRef, Verdict
from environments.benchmarks.harness.budget import Budget, BudgetMeter
from environments.benchmarks.harness.recorder import (
    append_row,
    build_row,
    classify_outcome,
    detect_refusal,
)
from environments.benchmarks.harness.scaffolds import (
    ReactResult,
    run_react_loop,
    run_stage2_loop,
    system_prompt_for,
)

logger = logging.getLogger("scarlight.harness.runner")

VALID_MODES = ("system", "model-swap")
VALID_SCAFFOLDS = ("stage1", "stage2", "inspect")
_AUTO = "__auto__"


@dataclass
class RunResult:
    """Everything one :func:`run` invocation produced."""

    rows: List[Dict[str, Any]] = field(default_factory=list)
    scoreboard_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    manifest: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)


# -- helpers ---------------------------------------------------------------
def git_commit(short: bool = True) -> str:
    """Best-effort ``harness_commit`` stamp; ``"unknown"`` outside a repo."""
    try:
        args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
        out = subprocess.run(
            args,
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = out.stdout.strip()
        return commit or "unknown"
    except Exception:
        return "unknown"


def _looks_like_client(obj: Any) -> bool:
    """True if ``obj`` is a ready OpenAI-shaped client (e.g. a StubModel)."""
    chat = getattr(obj, "chat", None)
    completions = getattr(chat, "completions", None)
    return callable(getattr(completions, "create", None))


def _resolve_client(model: str, base_url: Optional[str], api_key: Optional[str]) -> Any:
    """Build a real OpenAI-compatible client (lazy; only on the live path)."""
    base_url = base_url or os.getenv("SCARLIGHT_BENCH_BASE_URL") or "https://openrouter.ai/api/v1"
    api_key = (
        api_key
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key)


def _resolve_budget(budget: Any, rung: str) -> Budget:
    if budget is None:
        return Budget.preset(rung)
    return Budget.from_dict(budget)


def _write_transcript(out_dir: Optional[Path], task: TaskRef, seed: int, attempt: int, react: ReactResult) -> Optional[str]:
    if out_dir is None:
        return None
    safe = task.task_id.replace(":", "_").replace("/", "_")
    path = out_dir / "transcripts" / f"{safe}.s{seed}.a{attempt}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(react.transcript, f, ensure_ascii=False, indent=2)
        return str(path)
    except Exception:
        logger.debug("could not write transcript", exc_info=True)
        return None


# -- the attempt ----------------------------------------------------------
def _run_attempt(
    *,
    adapter,
    client: Any,
    model_name: str,
    provider: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    task: TaskRef,
    seed: int,
    attempt: int,
    k: int,
    mode: str,
    scaffold: str,
    budget: Budget,
    out_dir: Optional[Path],
    cost_fn: Optional[Callable[..., Any]],
    clock: Optional[Callable[[], float]],
    judge: Optional[Callable[..., Any]],
    harness_commit: str,
    contamination: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one (task, seed, attempt) and return its result row."""
    if hasattr(client, "reset"):
        try:
            client.reset(seed=seed, attempt=attempt)
        except TypeError:
            client.reset()  # tolerate a no-arg reset

    meter = BudgetMeter(
        budget,
        model=model_name,
        provider=provider,
        base_url=base_url,
        cost_fn=cost_fn,
        clock=clock,
    )
    harness_error = False
    react = ReactResult()
    env = None
    verdict = Verdict(passed=False)
    try:
        env = adapter.prepare(task)
        objective = adapter.objective(task)
        system_prompt = system_prompt_for(task.rung)

        def probe() -> bool:
            try:
                return bool(adapter.score(task, env).passed)
            except Exception:
                return False

        react = _drive_scaffold(
            scaffold=scaffold,
            client=client,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            system_prompt=system_prompt,
            objective=objective,
            env=env,
            meter=meter,
            success_probe=probe,
        )
        verdict = adapter.score(task, env)
    except Exception as exc:  # noqa: BLE001 - a harness crash is its own outcome
        logger.exception("harness error on %s seed=%s attempt=%s: %s", task.task_id, seed, attempt, exc)
        harness_error = True
        react.final_text = react.final_text or f"<harness error: {exc}>"
    finally:
        if env is not None:
            try:
                adapter.cleanup(task, env)
            except Exception:
                logger.debug("adapter.cleanup raised", exc_info=True)

    refused = detect_refusal(react.final_text, made_tool_calls=react.tool_calls_made > 0)
    outcome = classify_outcome(
        passed=verdict.passed,
        budget_reason=react.budget_reason,
        refused=refused,
        harness_error=harness_error,
    )
    # Snapshot every scoring-derived value BEFORE the (operator-supplied) judge
    # runs, so a buggy or adversarial judge that mutates the live verdict OR the
    # react result can never change the recorded machine numbers — judge_signal
    # is secondary only. (Both subtask_completion AND first_solve_turn must be
    # captured here; first_solve_turn rides on the mutable react object.)
    subtask_completion = verdict.subtask_completion
    first_solve_turn = react.first_solve_turn if outcome == "solved" else None

    judge_signal = None
    if judge is not None:
        try:
            judge_signal = judge(task=task, env=env, react=react, verdict=verdict)
        except Exception:
            logger.debug("judge raised; recording null judge_signal", exc_info=True)

    transcript_path = _write_transcript(out_dir, task, seed, attempt, react)

    return build_row(
        task=task,
        seed=seed,
        attempt=attempt,
        k=k,
        mode=mode,
        scaffold=scaffold,
        model=model_name,
        budget=budget,
        outcome_class=outcome,
        first_solve_turn=first_solve_turn,
        subtask_completion=subtask_completion,
        cost=meter.cost_snapshot(),
        contamination=contamination,
        judge_signal=judge_signal,
        transcript_path=transcript_path,
        harness_commit=harness_commit,
    )


def _drive_scaffold(
    *,
    scaffold: str,
    client: Any,
    model_name: str,
    base_url: Optional[str],
    api_key: Optional[str],
    system_prompt: str,
    objective: str,
    env,
    meter: BudgetMeter,
    success_probe: Callable[[], bool],
) -> ReactResult:
    """Select and run the inner loop for ``scaffold``.

    A ready client (a StubModel, or a pre-built OpenAI client) is always driven
    through the ReAct loop — that is the only way to drive an arbitrary client —
    and the row still records the *requested* scaffold. The ``stage2``/``inspect``
    live drivers are reached only when the runner was handed a model *name*
    (string) and resolved its own client.
    """
    if client is not None and scaffold == "stage1":
        return run_react_loop(
            client=client,
            model=model_name,
            system_prompt=system_prompt,
            objective=objective,
            env=env,
            meter=meter,
            success_probe=success_probe,
        )
    if client is not None and scaffold in ("stage2", "inspect"):
        # Field-recording path: a ready client cannot drive AIAgent/Inspect, so
        # use ReAct but keep the requested label (validation.md §11.1).
        logger.info("scaffold=%s with a ready client: driving via ReAct (label preserved)", scaffold)
        return run_react_loop(
            client=client,
            model=model_name,
            system_prompt=system_prompt,
            objective=objective,
            env=env,
            meter=meter,
            success_probe=success_probe,
        )
    if scaffold == "stage2":
        return run_stage2_loop(
            env=env,
            objective=objective,
            model=model_name,
            meter=meter,
            base_url=base_url,
            api_key=api_key,
            success_probe=success_probe,
        )
    if scaffold == "inspect":
        from environments.benchmarks.harness.inspect_bridge import run_inspect_loop

        return run_inspect_loop(
            env=env,
            objective=objective,
            model=model_name,
            meter=meter,
            system_prompt=system_prompt,
            base_url=base_url,
            api_key=api_key,
            success_probe=success_probe,
        )
    # stage1 with a model name: resolve a real client, then ReAct.
    resolved = _resolve_client(model_name, base_url, api_key)
    return run_react_loop(
        client=resolved,
        model=model_name,
        system_prompt=system_prompt,
        objective=objective,
        env=env,
        meter=meter,
        success_probe=success_probe,
    )


# -- programmatic API ------------------------------------------------------
def run(
    adapter,
    model: Any,
    *,
    seeds: int = 1,
    k: int = 1,
    budget: Any = None,
    mode: str = "model-swap",
    scaffold: str = "stage1",
    out_dir: Any = None,
    slice_name: str = "all",
    first_n: Optional[int] = None,
    tasks: Optional[List[TaskRef]] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    judge: Optional[Callable[..., Any]] = None,
    cost_fn: Optional[Callable[..., Any]] = None,
    clock: Optional[Callable[[], float]] = None,
    harness_commit: Optional[str] = None,
    contamination_cutoff: Any = _AUTO,
    overwrite: bool = True,
    scoreboard_name: str = "scoreboard.jsonl",
    write: bool = True,
) -> RunResult:
    """Run ``adapter`` under ``model`` and return the recorded rows + manifest.

    ``model`` may be a ready client (a StubModel for Tier 0, or any
    OpenAI-shaped client) or a model-name string (the live path). ``seeds`` and
    ``k`` give the N-seed / pass@k grid. With ``write`` (default), a
    ``scoreboard.jsonl`` and a ``manifest.json`` are written under ``out_dir``
    (a fresh temp dir if unset), and ``transcript_path`` is populated.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    if scaffold not in VALID_SCAFFOLDS:
        raise ValueError(f"scaffold must be one of {VALID_SCAFFOLDS}, got {scaffold!r}")

    # Resolve client vs. model name.
    if _looks_like_client(model):
        client: Any = model
        resolved_model_name = model_name or getattr(model, "model_name", None) or "claude-sonnet-4-6"
    else:
        client = None
        resolved_model_name = model_name or str(model)
    provider = provider or contam._infer_provider(resolved_model_name)

    # Output locations.
    out_path: Optional[Path] = None
    if write:
        out_path = Path(out_dir) if out_dir is not None else Path(tempfile.mkdtemp(prefix="scarlight_bench_"))
        out_path.mkdir(parents=True, exist_ok=True)
    elif out_dir is not None:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
    scoreboard_path = (out_path / scoreboard_name) if out_path is not None else None
    if scoreboard_path is not None and overwrite and scoreboard_path.exists():
        scoreboard_path.unlink()

    budget_obj = _resolve_budget(budget, getattr(adapter, "rung", "_default"))

    # Task slice (+ surface any silent cap from --first-n in the manifest).
    all_tasks = list(tasks) if tasks is not None else list(adapter.list_tasks(slice_name))
    dropped: List[str] = []
    if first_n is not None and first_n < len(all_tasks):
        dropped = [t.task_id for t in all_tasks[first_n:]]
        all_tasks = all_tasks[:first_n]

    commit = harness_commit or git_commit()

    # Contamination cutoff: auto-resolve from the model unless given explicitly.
    if contamination_cutoff == _AUTO:
        cutoff = contam.resolve_model_cutoff(resolved_model_name, provider)
    else:
        cutoff = contamination_cutoff

    rows: List[Dict[str, Any]] = []
    for task in all_tasks:
        task_contam = contam.classify(cutoff, task.published)
        for seed in range(seeds):
            for attempt in range(k):
                row = _run_attempt(
                    adapter=adapter,
                    client=client,
                    model_name=resolved_model_name,
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    task=task,
                    seed=seed,
                    attempt=attempt,
                    k=k,
                    mode=mode,
                    scaffold=scaffold,
                    budget=budget_obj,
                    out_dir=out_path,
                    cost_fn=cost_fn,
                    clock=clock,
                    judge=judge,
                    harness_commit=commit,
                    contamination=task_contam,
                )
                rows.append(row)
                if scoreboard_path is not None:
                    append_row(scoreboard_path, row)

    manifest = {
        "benchmark": getattr(adapter, "name", "unknown"),
        "rung": getattr(adapter, "rung", "unknown"),
        "slice": slice_name,
        "first_n": first_n,
        "seeds": seeds,
        "k": k,
        "mode": mode,
        "scaffold": scaffold,
        "model": resolved_model_name,
        "budget": budget_obj.to_dict(),
        "harness_commit": commit,
        "dropped_tasks": dropped,
        "n_tasks": len(all_tasks),
        "n_rows": len(rows),
    }
    manifest_path: Optional[Path] = None
    if out_path is not None:
        manifest_path = out_path / "manifest.json"
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)

    return RunResult(rows=rows, scoreboard_path=scoreboard_path, manifest_path=manifest_path, manifest=manifest)


# -- CLI -------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m environments.benchmarks.harness.runner",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--benchmark", default=None, help="Registered adapter name (see --list)")
    p.add_argument("--slice", dest="slice_name", default="all", help="Named task slice")
    p.add_argument("--first-n", type=int, default=None, help="Cap to the first N tasks (logged to dropped_tasks)")
    p.add_argument("--seeds", type=int, default=5, help="N seeds (>=5 for a publishable headline)")
    p.add_argument("-k", type=int, default=1, help="Attempts per seed (pass@k)")
    p.add_argument("--mode", choices=VALID_MODES, default="model-swap")
    p.add_argument("--scaffold", choices=VALID_SCAFFOLDS, default="stage1")
    p.add_argument("--model", default="anthropic:claude-sonnet-4-6", help="Model spec for the agent")
    p.add_argument("--provider", default=None)
    p.add_argument("--api-base-url", dest="base_url", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--budget", default=None, help='JSON, e.g. {"max_turns":40,"max_usd":1.0}')
    p.add_argument("--max-usd", type=float, default=None, help="Override budget.max_usd")
    p.add_argument("--config", default=None,
                   help="JSON kwargs forwarded verbatim to the adapter constructor "
                        "(adapter-specific; see the chosen adapter's docstring)")
    p.add_argument("--out-dir", type=Path, default=Path("out/scarlight_bench"))
    p.add_argument("--overwrite", action="store_true", help="Truncate an existing scoreboard first")
    p.add_argument("--list", action="store_true", help="List registered benchmarks and exit")
    return p.parse_args(argv)


def _load_registry():
    """Import the out-of-tree adapter registration module (no names here)."""
    import importlib

    importlib.import_module("environments.benchmarks.adapters")
    from environments.benchmarks.harness import registry

    return registry


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args(argv)
    registry = _load_registry()

    if args.list:
        print("Registered benchmarks:", ", ".join(registry.available()))
        return 0

    if not args.benchmark:
        print("error: --benchmark is required (see --list)", file=sys.stderr)
        return 2

    adapter_kwargs: Dict[str, Any] = {}
    if args.config:
        adapter_kwargs = json.loads(args.config)
    try:
        adapter = registry.load(args.benchmark, **adapter_kwargs)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    budget_dict: Optional[Dict[str, Any]] = None
    if args.budget:
        budget_dict = json.loads(args.budget)
    if args.max_usd is not None:
        budget_dict = dict(budget_dict or {})
        budget_dict["max_usd"] = args.max_usd

    result = run(
        adapter,
        args.model,
        seeds=args.seeds,
        k=args.k,
        budget=budget_dict,
        mode=args.mode,
        scaffold=args.scaffold,
        out_dir=args.out_dir,
        slice_name=args.slice_name,
        first_n=args.first_n,
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        overwrite=args.overwrite,
    )
    logger.info(
        "Done. %d row(s) → %s (manifest: %s)",
        len(result.rows),
        result.scoreboard_path,
        result.manifest_path,
    )
    if result.manifest.get("dropped_tasks"):
        logger.info("Dropped %d task(s) via --first-n: %s",
                    len(result.manifest["dropped_tasks"]), result.manifest["dropped_tasks"][:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

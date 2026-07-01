"""Aggregate ``scoreboard.jsonl`` into a per-benchmark / per-mode table.

The report is where the rigor controls become a *number you can read*: ``pass@1``,
``pass@k``, ``success@budget``, ``mean±std`` over seeds, median ``first_solve_turn``,
total cost, and a contamination summary (``requirements.md`` §5).

The one hard rule it enforces: a ``system`` number and a ``model-swap`` number
measure *different things* and must never be averaged together
(``validation.md`` §11.2). Aggregation is always grouped by ``(benchmark, rung,
mode, scaffold, model)``; :func:`assert_no_cross_mode` is the guard that raises
if a caller asks for a single mean spanning more than one mode.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from environments.benchmarks.harness.recorder import load_rows

SOLVED = "solved"
GROUP_KEYS = ("benchmark", "rung", "mode", "scaffold", "model")


class CrossModeAggregationError(ValueError):
    """Raised when an aggregation would average across distinct ``mode`` values."""


def assert_no_cross_mode(rows: Iterable[Dict[str, Any]]) -> None:
    """Raise if ``rows`` span more than one ``mode`` (§11.2)."""
    modes = {r.get("mode") for r in rows}
    if len(modes) > 1:
        raise CrossModeAggregationError(
            f"refusing to aggregate across modes {sorted(m for m in modes if m)}; "
            "system and model-swap numbers are not comparable"
        )


def _group_key(row: Dict[str, Any]) -> Tuple:
    return tuple(row.get(k) for k in GROUP_KEYS)


def _seed_pass_fraction(attempts: List[Dict[str, Any]], *, max_attempt: Optional[int] = None) -> float:
    """1.0 if any (optionally first ``max_attempt+1``) attempt solved, else 0.0."""
    relevant = attempts if max_attempt is None else [a for a in attempts if a.get("attempt", 0) <= max_attempt]
    return 1.0 if any(a.get("outcome_class") == SOLVED for a in relevant) else 0.0


def aggregate_group(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate rows that share one (benchmark, rung, mode, scaffold, model).

    pass@k collapses attempts within a seed (any solved → seed passes), then
    averages across seeds — the N-seed mean±std that a publishable headline
    requires.
    """
    assert_no_cross_mode(rows)
    by_seed: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_seed[r.get("seed")].append(r)

    k = max((r.get("k") or 1) for r in rows)
    pass1_per_seed = [_seed_pass_fraction(att, max_attempt=0) for att in by_seed.values()]
    passk_per_seed = [_seed_pass_fraction(att) for att in by_seed.values()]

    solved_rows = [r for r in rows if r.get("outcome_class") == SOLVED]
    fst_values = [r["first_solve_turn"] for r in solved_rows if r.get("first_solve_turn") is not None]

    usd_values = [r.get("cost", {}).get("usd") for r in rows]
    total_usd = sum(v for v in usd_values if isinstance(v, (int, float)))

    outcome_counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        outcome_counts[r.get("outcome_class", "unknown")] += 1

    contam_counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        contam_counts[r.get("contamination", {}).get("flag", "unknown")] += 1

    n_seeds = len(by_seed)
    return {
        "benchmark": rows[0].get("benchmark"),
        "rung": rows[0].get("rung"),
        "mode": rows[0].get("mode"),
        "scaffold": rows[0].get("scaffold"),
        "model": rows[0].get("model"),
        "n_seeds": n_seeds,
        "k": k,
        "pass@1": statistics.fmean(pass1_per_seed) if pass1_per_seed else 0.0,
        "pass@k": statistics.fmean(passk_per_seed) if passk_per_seed else 0.0,
        "mean": statistics.fmean(passk_per_seed) if passk_per_seed else 0.0,
        "std": statistics.pstdev(passk_per_seed) if len(passk_per_seed) > 1 else 0.0,
        "success@budget": statistics.fmean(passk_per_seed) if passk_per_seed else 0.0,
        "median_first_solve_turn": statistics.median(fst_values) if fst_values else None,
        "outcome_counts": dict(outcome_counts),
        "contamination": dict(contam_counts),
        "total_usd": round(total_usd, 6),
        "publishable": n_seeds >= 5,
    }


def build_table(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group rows and aggregate each group into one table row.

    Always split by mode (and benchmark/scaffold/model), so the table can never
    fold a system number into a model-swap number.
    """
    groups: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[_group_key(r)].append(r)
    table = [aggregate_group(group) for group in groups.values()]
    table.sort(key=lambda d: (d["benchmark"] or "", d["mode"] or "", d["scaffold"] or "", d["model"] or ""))
    return table


def format_table(table: List[Dict[str, Any]]) -> str:
    """A compact text rendering of the aggregate table."""
    if not table:
        return "(no rows)"
    lines = []
    header = (
        f"{'benchmark':<12} {'mode':<11} {'scaffold':<9} {'model':<26} "
        f"{'N':>2} {'k':>2} {'pass@1':>7} {'pass@k':>7} {'mean±std':>13} {'FST':>5} {'cost$':>8} {'contam':>16}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for t in table:
        contam = ",".join(f"{k}={v}" for k, v in sorted(t["contamination"].items()))
        fst = "" if t["median_first_solve_turn"] is None else f"{t['median_first_solve_turn']:.0f}"
        lines.append(
            f"{(t['benchmark'] or ''):<12} {(t['mode'] or ''):<11} {(t['scaffold'] or ''):<9} "
            f"{(t['model'] or ''):<26.26} {t['n_seeds']:>2} {t['k']:>2} "
            f"{t['pass@1']:>7.3f} {t['pass@k']:>7.3f} "
            f"{t['mean']:>6.3f}±{t['std']:<6.3f} {fst:>5} {t['total_usd']:>8.4f} {contam:>16.16}"
        )
        if not t["publishable"]:
            lines.append(f"    ⚠ draft: N={t['n_seeds']} < 5 seeds — not a publishable headline")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Aggregate a scarlight-bench scoreboard.")
    p.add_argument("scoreboard", type=Path, help="Path to scoreboard.jsonl")
    p.add_argument("--json", action="store_true", help="Emit the table as JSON")
    args = p.parse_args(argv)

    rows = load_rows(args.scoreboard)
    table = build_table(rows)
    if args.json:
        print(json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_table(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Tier 0 — two-axis modes (``validation.md`` §11) + reporting (§5 / §14).

Mode (``system`` vs ``model-swap``) and scaffold are recorded verbatim and never
cross-aggregated; the report renders the per-benchmark/per-mode table and flags
draft (N<5) headlines.
"""

from __future__ import annotations

import pytest

from doubles import MockAdapter, StubModel

from environments.benchmarks.harness import report, runner


# -- §11.1 mode recorded ----------------------------------------------------
def test_mode_and_scaffold_are_recorded(tmp_path):
    r1 = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                    mode="model-swap", scaffold="stage1", out_dir=tmp_path / "a")
    assert r1.rows[0]["mode"] == "model-swap"
    assert r1.rows[0]["scaffold"] == "stage1"

    r2 = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                    mode="system", scaffold="stage2", out_dir=tmp_path / "b")
    assert r2.rows[0]["mode"] == "system"
    assert r2.rows[0]["scaffold"] == "stage2"


def test_invalid_mode_or_scaffold_rejected(tmp_path):
    with pytest.raises(ValueError):
        runner.run(MockAdapter(), StubModel("solve"), mode="bogus", out_dir=tmp_path)
    with pytest.raises(ValueError):
        runner.run(MockAdapter(), StubModel("solve"), scaffold="bogus", out_dir=tmp_path)


# -- §11.2 no cross-mode aggregation ---------------------------------------
def test_report_separates_modes(tmp_path):
    system = runner.run(MockAdapter(), StubModel("solve"), seeds=2, k=1,
                        mode="system", scaffold="stage2", out_dir=tmp_path / "s").rows
    swap = runner.run(MockAdapter(), StubModel("fail"), seeds=2, k=1,
                      mode="model-swap", scaffold="stage1", out_dir=tmp_path / "m").rows
    table = report.build_table(system + swap)
    modes = sorted(t["mode"] for t in table)
    assert modes == ["model-swap", "system"]  # two separate sections, never merged
    # and they carry different numbers (system solved, swap failed)
    by_mode = {t["mode"]: t for t in table}
    assert by_mode["system"]["pass@1"] == 1.0
    assert by_mode["model-swap"]["pass@1"] == 0.0


def test_report_refuses_to_average_across_modes(tmp_path):
    system = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                        mode="system", scaffold="stage2", out_dir=tmp_path / "s").rows
    swap = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                      mode="model-swap", scaffold="stage1", out_dir=tmp_path / "m").rows
    with pytest.raises(report.CrossModeAggregationError):
        report.aggregate_group(system + swap)
    with pytest.raises(report.CrossModeAggregationError):
        report.assert_no_cross_mode(system + swap)


# -- §5 / §14 reporting columns + publishability ---------------------------
def test_report_has_required_columns(tmp_path):
    rows = runner.run(MockAdapter(), StubModel("solve"), seeds=5, k=1, out_dir=tmp_path).rows
    agg = report.build_table(rows)[0]
    for col in ("pass@1", "pass@k", "success@budget", "mean", "std",
                "median_first_solve_turn", "total_usd", "contamination", "n_seeds"):
        assert col in agg
    assert agg["publishable"] is True  # N >= 5


def test_under_five_seeds_is_draft(tmp_path):
    rows = runner.run(MockAdapter(), StubModel("solve"), seeds=3, k=1, out_dir=tmp_path).rows
    agg = report.build_table(rows)[0]
    assert agg["publishable"] is False  # N < 5 → draft, not a headline


def test_format_table_renders(tmp_path):
    rows = runner.run(MockAdapter(), StubModel("solve"), seeds=5, k=1, out_dir=tmp_path).rows
    text = report.format_table(report.build_table(rows))
    assert "pass@1" in text and "mock" in text

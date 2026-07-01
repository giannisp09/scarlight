"""Tier 0 — contamination tagging (``validation.md`` §10).

The harness tags ``suspect`` when a task predates the model cutoff and ``clean``
otherwise; either way the run is NOT blocked — a row is always produced.
"""

from __future__ import annotations

from doubles import MockAdapter, StubModel

from environments.benchmarks.harness import runner
from environments.benchmarks.harness.contamination import CLEAN, SUSPECT, UNKNOWN, classify


# -- the pure classifier ----------------------------------------------------
def test_pre_cutoff_task_is_suspect():
    assert classify("2026-01", "2024-06")["flag"] == SUSPECT


def test_post_cutoff_task_is_clean():
    assert classify("2026-01", "2026-05")["flag"] == CLEAN


def test_same_month_is_suspect():
    # published <= cutoff (could be in training data)
    assert classify("2026-01", "2026-01")["flag"] == SUSPECT


def test_missing_dates_are_unknown():
    assert classify(None, "2024-06")["flag"] == UNKNOWN
    assert classify("2026-01", None)["flag"] == UNKNOWN
    assert classify(None, None)["flag"] == UNKNOWN


def test_classify_records_both_dates():
    block = classify("2026-01", "2024-06")
    assert block["model_cutoff"] == "2026-01"
    assert block["task_published"] == "2024-06"


# -- end to end through the runner (and never blocks) ----------------------
def test_run_tags_suspect_but_still_produces_row(tmp_path):
    adapter = MockAdapter(published="2024-06")
    result = runner.run(adapter, StubModel("solve"), seeds=1, k=1,
                        contamination_cutoff="2026-01", out_dir=tmp_path)
    assert len(result.rows) == 1  # NOT blocked
    assert result.rows[0]["contamination"]["flag"] == SUSPECT


def test_run_tags_clean_for_post_cutoff_task(tmp_path):
    adapter = MockAdapter(published="2026-05")
    result = runner.run(adapter, StubModel("solve"), seeds=1, k=1,
                        contamination_cutoff="2026-01", out_dir=tmp_path)
    assert len(result.rows) == 1
    assert result.rows[0]["contamination"]["flag"] == CLEAN

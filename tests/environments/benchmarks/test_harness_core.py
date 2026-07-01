"""Tier 0 — harness core: protocol round-trip, schema, reproducibility, manifest.

Covers ``validation.md`` §2 (harness core), §9 (reproducibility + manifest). All
checks run with zero LLM calls via the :mod:`doubles`.
"""

from __future__ import annotations

import json

import pytest

from doubles import MockAdapter, StubModel

from environments.benchmarks.harness import runner
from environments.benchmarks.harness.budget import Budget
from environments.benchmarks.harness.recorder import (
    SCHEMA_VERSION,
    SchemaError,
    load_schema,
    validate_row,
)

REQUIRED = [
    "schema", "benchmark", "rung", "task_id", "seed", "attempt", "mode",
    "scaffold", "model", "budget", "outcome_class", "first_solve_turn",
    "subtask_completion", "cost", "judge_signal", "contamination",
    "transcript_path", "harness_commit",
]


# -- §2.1 protocol round-trip ----------------------------------------------
def test_protocol_roundtrip_solved(tmp_path):
    """runner.run(MockAdapter, StubModel(solve)) → exactly one solved v1 row."""
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["schema"] == SCHEMA_VERSION == "scarlight-bench/v1"
    assert row["outcome_class"] == "solved"

    # exactly one line on disk
    lines = [ln for ln in result.scoreboard_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    # all required fields present and non-null, except the nullable judge_signal
    for field in REQUIRED:
        assert field in row, f"missing {field}"
        if field != "judge_signal":
            assert row[field] is not None, f"{field} unexpectedly null"


def test_roundtrip_row_is_schema_valid(tmp_path):
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    validate_row(result.rows[0])  # must not raise


# -- §2.2 schema conformance -----------------------------------------------
def test_every_emitted_row_validates(tmp_path):
    result = runner.run(MockAdapter(n_tasks=2), StubModel("solve"), seeds=2, k=2, out_dir=tmp_path)
    assert len(result.rows) == 8
    for row in result.rows:
        validate_row(row)


def test_missing_required_field_fails_schema(tmp_path):
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    for field in ("outcome_class", "cost", "budget", "contamination", "harness_commit"):
        bad = dict(result.rows[0])
        bad.pop(field)
        with pytest.raises(SchemaError):
            validate_row(bad)


def test_bad_outcome_class_fails_schema(tmp_path):
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    bad = dict(result.rows[0])
    bad["outcome_class"] = "totally_made_up"
    with pytest.raises(SchemaError):
        validate_row(bad)


def test_unexpected_field_fails_schema(tmp_path):
    """additionalProperties:false — junk/typo'd top-level keys are rejected."""
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    bad = dict(result.rows[0])
    bad["totally_unexpected_field"] = None
    with pytest.raises(SchemaError):
        validate_row(bad)


def test_optional_k_field_is_allowed(tmp_path):
    """The defined optional `k` rides alongside the required set (not rejected)."""
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    assert "k" in result.rows[0]
    validate_row(result.rows[0])  # k present, still valid


def test_schema_file_is_checked_in_and_loads():
    schema = load_schema()
    assert schema["title"].startswith("scarlight-bench/v1")
    assert set(REQUIRED).issubset(set(schema["required"]))


# -- §9.1 deterministic inputs ---------------------------------------------
def _normalize(row):
    """Drop the only fields allowed to vary run-to-run (wall-clock)."""
    row = json.loads(json.dumps(row))  # deep copy
    row["cost"]["wall_clock_s"] = 0.0
    return json.dumps(row, sort_keys=True)


def test_reproducible_rows_byte_identical(tmp_path):
    """Two runs with the same seed+StubModel → byte-identical rows (sans wall-clock)."""
    r1 = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                    out_dir=tmp_path, harness_commit="testcommit")
    r2 = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                    out_dir=tmp_path, overwrite=True, harness_commit="testcommit")
    assert _normalize(r1.rows[0]) == _normalize(r2.rows[0])
    assert r1.rows[0]["harness_commit"] == r2.rows[0]["harness_commit"] == "testcommit"


def test_harness_commit_is_stamped(tmp_path):
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1, out_dir=tmp_path)
    assert isinstance(result.rows[0]["harness_commit"], str)
    assert result.rows[0]["harness_commit"]  # non-empty


# -- §9.2 manifest completeness --------------------------------------------
def test_manifest_records_all_run_parameters(tmp_path):
    result = runner.run(MockAdapter(n_tasks=1), StubModel("solve"), seeds=3, k=2,
                        mode="model-swap", scaffold="stage1",
                        budget=Budget(max_turns=40), out_dir=tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for key in ("benchmark", "slice", "first_n", "seeds", "k", "mode", "scaffold",
                "model", "budget", "harness_commit", "dropped_tasks"):
        assert key in manifest, f"manifest missing {key}"
    assert manifest["seeds"] == 3 and manifest["k"] == 2


def test_first_n_cap_is_recorded_in_dropped_tasks(tmp_path):
    """A --first-n truncation must surface in dropped_tasks — no silent cap."""
    result = runner.run(MockAdapter(n_tasks=5), StubModel("solve"), seeds=1, k=1,
                        first_n=2, out_dir=tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["first_n"] == 2
    assert len(manifest["dropped_tasks"]) == 3
    assert set(manifest["dropped_tasks"]) == {"mock/task_2", "mock/task_3", "mock/task_4"}
    # and only the kept tasks produced rows
    assert {r["task_id"] for r in result.rows} == {"mock/task_0", "mock/task_1"}

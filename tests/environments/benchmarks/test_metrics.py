"""Tier 0 — metrics correctness (``validation.md`` §3): the heart of objective
verification. pass@k, seed variance, budget_exhausted≠failed, max_usd hard cap,
cost accuracy, refusal classification — all driven by deterministic doubles.
"""

from __future__ import annotations

from decimal import Decimal

from doubles import MockAdapter, StubModel

from environments.benchmarks.harness import report, runner
from environments.benchmarks.harness.budget import Budget


# -- §3.1 pass@k -----------------------------------------------------------
def test_pass_at_k_passes_only_on_third_attempt(tmp_path):
    result = runner.run(MockAdapter(), StubModel("pass_on_attempt", which_attempt=2),
                        seeds=1, k=5, out_dir=tmp_path)
    agg = report.build_table(result.rows)[0]
    assert agg["pass@1"] == 0.0
    assert agg["pass@k"] == 1.0
    assert agg["k"] == 5
    solved = [r for r in result.rows if r["outcome_class"] == "solved"]
    assert len(solved) == 1
    assert solved[0]["attempt"] == 2  # the 3rd attempt (0-indexed)
    assert solved[0]["first_solve_turn"] is not None


# -- §3.2 variance over seeds ----------------------------------------------
def test_variance_over_seeds(tmp_path):
    result = runner.run(MockAdapter(), StubModel("pass_on_seeds", pass_seeds={0, 2, 4}),
                        seeds=5, k=1, out_dir=tmp_path)
    agg = report.build_table(result.rows)[0]
    assert abs(agg["mean"] - 0.6) < 1e-9
    assert agg["n_seeds"] == 5
    # std matches numpy.std (population, ddof=0) on the per-seed pass vector
    expected_std = (0.6 * (1 - 0.6) ** 2 + 0.4 * (0 - 0.6) ** 2) ** 0.5
    assert abs(agg["std"] - expected_std) < 1e-9


# -- §3.3 budget_exhausted ≠ failed ----------------------------------------
def test_budget_exhausted_is_distinct_from_failed(tmp_path):
    result = runner.run(MockAdapter(), StubModel("loop"), seeds=1, k=1,
                        budget=Budget(max_turns=3, max_usd=None), out_dir=tmp_path)
    row = result.rows[0]
    assert row["outcome_class"] == "budget_exhausted"
    assert row["outcome_class"] != "failed"
    assert row["first_solve_turn"] is None


def test_budget_stops_at_the_turn_ceiling(tmp_path):
    """A loop-forever model under max_turns=3 makes exactly 3 model calls."""
    stub = StubModel("loop")
    runner.run(MockAdapter(), stub, seeds=1, k=1,
               budget=Budget(max_turns=3, max_usd=None), out_dir=tmp_path)
    assert stub.calls == 3


# -- §3.4 max_usd hard cap (per-task abort, not whole-run) ------------------
def test_max_usd_aborts_task_before_overbudget_call(tmp_path):
    def fixed_cost(model, usage, **kwargs):
        return Decimal("0.40")

    result = runner.run(MockAdapter(n_tasks=2), StubModel("loop"), seeds=1, k=1,
                        budget=Budget(max_turns=100, max_usd=0.50),
                        cost_fn=fixed_cost, out_dir=tmp_path)
    assert len(result.rows) == 2  # other tasks in the slice still ran
    for row in result.rows:
        assert row["outcome_class"] == "budget_exhausted"
        assert row["cost"]["usd"] <= 0.50  # never exceeded the cap


def test_max_usd_allows_first_call_then_aborts(tmp_path):
    """Cap below the projected 2nd call: exactly one call lands, then abort."""
    def fixed_cost(model, usage, **kwargs):
        return Decimal("0.40")

    stub = StubModel("loop")
    runner.run(MockAdapter(), stub, seeds=1, k=1,
               budget=Budget(max_turns=100, max_usd=0.50), cost_fn=fixed_cost, out_dir=tmp_path)
    assert stub.calls == 1


def test_max_usd_trips_when_actual_spend_reaches_cap(tmp_path):
    """Two $0.25 calls reach a $0.50 cap exactly, then the meter trips — no 3rd call."""
    def cost(model, usage, **kwargs):
        return Decimal("0.25")

    stub = StubModel("loop")
    result = runner.run(MockAdapter(), stub, seeds=1, k=1,
                        budget=Budget(max_turns=100, max_usd=0.50), cost_fn=cost, out_dir=tmp_path)
    assert stub.calls == 2
    assert result.rows[0]["outcome_class"] == "budget_exhausted"
    assert result.rows[0]["cost"]["usd"] <= 0.50


def test_unknown_pricing_disables_usd_cap_and_records_null(tmp_path):
    """If pricing is unknown, the $ cap is inert (run bounded by turns) and usd is honestly null."""
    def no_price(model, usage, **kwargs):
        return None

    stub = StubModel("loop")
    result = runner.run(MockAdapter(), stub, seeds=1, k=1,
                        budget=Budget(max_turns=3, max_usd=0.0001), cost_fn=no_price, out_dir=tmp_path)
    row = result.rows[0]
    assert row["outcome_class"] == "budget_exhausted"  # stopped on turns, not $
    assert row["cost"]["usd"] is None  # honest: unknown pricing → null, not a fake 0
    assert stub.calls == 3  # the inert $ cap did not cut it short


# -- §3.5 cost accounting --------------------------------------------------
def test_cost_matches_usage_pricing(tmp_path):
    """Recorded usd matches agent/usage_pricing.py for the recorded tokens (±1%)."""
    from agent.usage_pricing import CanonicalUsage, estimate_usage_cost

    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                        model_name="claude-sonnet-4-6", provider="anthropic", out_dir=tmp_path)
    cost = result.rows[0]["cost"]
    assert cost["usd"] is not None
    assert cost["input_tokens"] > 0 and cost["output_tokens"] > 0
    assert cost["wall_clock_s"] >= 0

    independent = estimate_usage_cost(
        "claude-sonnet-4-6",
        CanonicalUsage(input_tokens=cost["input_tokens"], output_tokens=cost["output_tokens"]),
        provider="anthropic",
    )
    expected_usd = float(independent.amount_usd)
    assert abs(cost["usd"] - expected_usd) <= max(0.01 * expected_usd, 1e-9)


def test_cost_matches_hand_computed_rate(tmp_path):
    """Sanity: claude-sonnet-4-6 is $3/$15 per Mtok in the offline table."""
    result = runner.run(MockAdapter(), StubModel("solve"), seeds=1, k=1,
                        model_name="claude-sonnet-4-6", provider="anthropic", out_dir=tmp_path)
    cost = result.rows[0]["cost"]
    hand = cost["input_tokens"] * 3.0 / 1e6 + cost["output_tokens"] * 15.0 / 1e6
    assert abs(cost["usd"] - hand) <= max(0.01 * hand, 1e-9)


# -- §3.6 refusal classification -------------------------------------------
def test_refusal_is_distinct_and_counted_separately(tmp_path):
    result = runner.run(MockAdapter(), StubModel("refuse"), seeds=1, k=1, out_dir=tmp_path)
    row = result.rows[0]
    assert row["outcome_class"] == "refused"
    assert row["outcome_class"] not in ("failed", "solved")
    agg = report.build_table(result.rows)[0]
    assert agg["outcome_counts"].get("refused") == 1
    assert "failed" not in agg["outcome_counts"]

"""Tier 0 — benchmark-agnosticism (§6), ExploitGym refactor parity (§7),
Cybench enumeration (§8.1).

These exercise the four registered adapters *offline* — no cybergym, no Docker,
no Inspect — by importing the classes directly and driving the shared loop with
the Tier 0 doubles.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from doubles import FakeEnv, StubModel, generate_flag

from environments.benchmarks.cybench.adapter import DOMAINS, CybenchAdapter
from environments.benchmarks.exploitgym.adapter import ExploitGymAdapter
from environments.benchmarks.harness import registry, runner
from environments.benchmarks.harness.adapter import RUNGS, BenchmarkAdapter, TaskRef, is_adapter
from environments.benchmarks.harness.budget import Budget, BudgetMeter
from environments.benchmarks.harness.recorder import classify_outcome, validate_row
from environments.benchmarks.harness.scaffolds import run_react_loop, system_prompt_for
from environments.benchmarks.htb.adapter import HTBAdapter
from environments.benchmarks.xbow.adapter import XBOWAdapter

HARNESS_DIR = Path(__file__).resolve().parents[3] / "environments" / "benchmarks" / "harness"
BENCH_NAMES = re.compile(r"exploitgym|cybench|xbow|htb", re.IGNORECASE)
ALL_ADAPTERS = [ExploitGymAdapter, CybenchAdapter, XBOWAdapter, HTBAdapter]


# -- §6.1 no per-benchmark branching in core -------------------------------
def test_harness_core_names_no_benchmark():
    """grep -rniE 'exploitgym|cybench|xbow|htb' harness/ → zero matches."""
    offenders = []
    for path in sorted(HARNESS_DIR.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        if path.suffix not in (".py", ".json"):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if BENCH_NAMES.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, "benchmark names leaked into harness/:\n" + "\n".join(offenders)


def test_harness_core_names_no_benchmark_via_grep():
    """Belt-and-braces: the literal validation.md §6.1 command returns nothing."""
    proc = subprocess.run(
        ["grep", "-rniE", "exploitgym|cybench|xbow|htb", str(HARNESS_DIR)],
        capture_output=True, text=True,
    )
    # grep exits 1 (no match) on success here; exit 0 (match found) is a failure.
    assert proc.returncode == 1, f"grep found benchmark names in harness/:\n{proc.stdout}"


# Extended vocabulary — the literal §6.1 pattern only covers the 4 registry names,
# so a benchmark identifier in another vocabulary (cybergym/arvo/sekai/...) could
# slip benchmark identity into the core. This guard closes that blind spot.
BENCH_VOCAB = re.compile(r"cybergym|\barvo\b|\bsekai\b|\bglacier\b|boot2root|hackthebox|hkcert", re.IGNORECASE)


def test_harness_core_no_benchmark_vocabulary():
    offenders = []
    for path in sorted(HARNESS_DIR.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix not in (".py", ".json"):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BENCH_VOCAB.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, "benchmark vocabulary leaked into harness/:\n" + "\n".join(offenders)


def test_xbow_htb_dot_adapter_aliases():
    """validation.md §6.2 names xbow.Adapter / htb.Adapter — both resolve + are adapters."""
    from environments.benchmarks import htb, xbow

    assert is_adapter(xbow.Adapter())
    assert is_adapter(htb.Adapter())
    assert xbow.Adapter is XBOWAdapter
    assert htb.Adapter is HTBAdapter


# -- §6.2 protocol spans all rungs -----------------------------------------
def test_all_adapters_satisfy_protocol_and_declare_valid_rung():
    for cls in ALL_ADAPTERS:
        adapter = cls()
        assert isinstance(adapter, BenchmarkAdapter), f"{cls.__name__} not a BenchmarkAdapter"
        assert is_adapter(adapter)
        assert adapter.rung in RUNGS, f"{cls.__name__} bad rung {adapter.rung}"


def test_protocol_spans_four_distinct_rungs():
    rungs = {cls().rung for cls in ALL_ADAPTERS}
    assert rungs == {"exploit-dev", "ctf", "web-pentest", "kill-chain"}


def test_registry_resolves_all_four_by_name():
    import importlib

    importlib.import_module("environments.benchmarks.adapters")
    assert set(registry.available()) == {"exploitgym", "cybench", "xbow", "htb"}
    for name in ("exploitgym", "cybench", "xbow", "htb"):
        assert is_adapter(registry.load(name))


# -- §7.1 golden-run parity (pre- vs post-refactor loop) --------------------
def _legacy_run_loop(client, model, env, system_prompt, objective, max_turns):
    """A frozen copy of the pre-refactor Stage-1 loop, for parity comparison."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": objective},
    ]
    for _turn in range(1, max_turns + 1):
        resp = client.chat.completions.create(model=model, messages=messages, tools=[], timeout=300.0)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            break
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls]})
        done = False
        for tc in tool_calls:
            cmd = json.loads(tc.function.arguments).get("command", "")
            out = env.execute(cmd, timeout=None)
            if "SCARLIGHT_DONE" in out.get("output", ""):
                done = True
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps({"output": out.get("output", "")})})
        if done:
            break
    return messages


def test_exploitgym_refactor_is_parity_clean():
    flag = "flag{parity_golden_run}"
    adapter = ExploitGymAdapter(expected_flag=flag)
    task = TaskRef("user:parity/task", "exploitgym", "exploit-dev", description="parity")
    objective = adapter.objective(task)
    system_prompt = system_prompt_for("exploit-dev")

    # pre-refactor loop
    env_legacy = FakeEnv(planted_flag=flag)
    _legacy_run_loop(StubModel("solve"), "claude-sonnet-4-6", env_legacy, system_prompt, objective, 8)
    v_legacy = adapter.score(task, env_legacy)

    # post-refactor shared loop
    env_new = FakeEnv(planted_flag=flag)
    meter = BudgetMeter(Budget(max_turns=8, max_usd=None), model="claude-sonnet-4-6")
    run_react_loop(client=StubModel("solve"), model="claude-sonnet-4-6",
                   system_prompt=system_prompt, objective=objective, env=env_new, meter=meter)
    v_new = adapter.score(task, env_new)

    # identical captured flag and identical outcome_class
    assert v_legacy.observed == v_new.observed == flag
    assert v_legacy.passed == v_new.passed is True
    out_legacy = classify_outcome(passed=v_legacy.passed, budget_reason=None, refused=False, harness_error=False)
    out_new = classify_outcome(passed=v_new.passed, budget_reason=None, refused=False, harness_error=False)
    assert out_legacy == out_new == "solved"


# -- §7.2 CLI back-compat ---------------------------------------------------
def test_legacy_run_exploitgym_delegates_and_emits_v1_row(tmp_path, monkeypatch):
    from environments.benchmarks.exploitgym import run_exploitgym
    from environments.benchmarks.harness.adapter import Verdict

    def fake_prepare(self, task):
        return FakeEnv(planted_flag=generate_flag(task.task_id))

    def fake_score(self, task, env):
        obs = env.read_file("/workspace/flag.txt").strip()
        exp = generate_flag(task.task_id)
        return Verdict(passed=obs == exp, expected=exp, observed=obs)

    monkeypatch.setattr(ExploitGymAdapter, "prepare", fake_prepare)
    monkeypatch.setattr(ExploitGymAdapter, "score", fake_score)
    monkeypatch.setattr(ExploitGymAdapter, "cleanup", lambda self, task, env: None)
    monkeypatch.setattr(runner, "_resolve_client", lambda *a, **k: StubModel("solve"))

    args = run_exploitgym.parse_args([
        "user:cybergym/arvo_demo", "--model", "anthropic:claude-sonnet-4-6",
        "--out-dir", str(tmp_path), "--max-turns", "10",
    ])
    result = run_exploitgym.run_from_args(args)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["schema"] == "scarlight-bench/v1"
    assert row["benchmark"] == "exploitgym"
    assert row["rung"] == "exploit-dev"
    assert row["mode"] == "model-swap" and row["scaffold"] == "stage1"
    assert row["outcome_class"] == "solved"
    validate_row(row)


# -- §8.1 Cybench task enumeration -----------------------------------------
def test_cybench_enumerates_40_tasks_over_6_domains():
    adapter = CybenchAdapter()
    tasks = adapter.list_tasks("all")
    assert len(tasks) == 40
    domains = {t.meta["domain"] for t in tasks}
    assert domains == set(DOMAINS)
    assert len(domains) == 6


def test_cybench_order_is_deterministic():
    a = [t.task_id for t in CybenchAdapter().list_tasks("all")]
    b = [t.task_id for t in CybenchAdapter().list_tasks("all")]
    assert a == b
    assert len(set(a)) == 40  # no duplicates


def test_cybench_domain_slice_filters():
    crypto = CybenchAdapter().list_tasks("crypto")
    assert all(t.meta["domain"] == "crypto" for t in crypto)
    assert 0 < len(crypto) < 40


def test_deferred_adapters_raise_clearly_on_prepare():
    for cls in (XBOWAdapter, HTBAdapter):
        adapter = cls()
        task = adapter.list_tasks("all")[0]
        with pytest.raises(NotImplementedError):
            adapter.prepare(task)

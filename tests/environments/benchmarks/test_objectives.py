"""Tier 0 — objective authenticity, no hint leakage (``validation.md`` §5).

Directly encodes the XOR-demo anti-pattern lesson: ``objective(task)`` returns the
benchmark's own framing and must contain none of the flag value, the secret
path's contents, or a step-by-step solution. Author tradecraft is allowed only in
the labelled *scaffold* system prompt, never per task.
"""

from __future__ import annotations

from doubles import MockAdapter, generate_flag

from environments.benchmarks.harness.scaffolds import SCAFFOLD_SYSTEM_PROMPTS, system_prompt_for


def test_objective_no_hints_mock():
    adapter = MockAdapter(n_tasks=3)
    for task in adapter.list_tasks("all"):
        adapter.prepare(task)  # plant the flag
        objective = adapter.objective(task)
        flag = generate_flag(task.task_id)
        assert flag not in objective, "objective leaked the flag value"
        # no obvious step-by-step leakage of the solving DSL verbs
        for leak in ("capture", "tamper-expected", flag):
            assert leak not in objective


def test_scaffold_prompt_is_separate_from_objective():
    """Author guidance lives in the scaffold system prompt, not the objective."""
    adapter = MockAdapter()
    task = adapter.list_tasks("all")[0]
    objective = adapter.objective(task)
    scaffold = system_prompt_for(task.rung)
    # The exploit-dev tradecraft (heap chain etc.) belongs to the scaffold.
    assert "tcache" in SCAFFOLD_SYSTEM_PROMPTS["exploit-dev"]
    assert "tcache" not in objective


def test_scaffold_prompts_are_benchmark_agnostic():
    """No scaffold prompt may name a specific benchmark (keeps §6.1 honest)."""
    for prompt in SCAFFOLD_SYSTEM_PROMPTS.values():
        low = prompt.lower()
        for name in ("exploitgym", "cybench", "xbow", "htb"):
            assert name not in low


# -- §5 sweep over EVERY registered adapter --------------------------------
def _registered_adapter_instances():
    from environments.benchmarks.cybench.adapter import CybenchAdapter
    from environments.benchmarks.exploitgym.adapter import ExploitGymAdapter
    from environments.benchmarks.htb.adapter import HTBAdapter
    from environments.benchmarks.xbow.adapter import XBOWAdapter

    secret = "flag{INJECTED_SECRET_should_never_appear}"
    # Wire the secret to REAL task ids so list_tasks() is non-empty and the
    # injected-as-expected-flag round-trip actually has teeth (a prior version
    # was vacuous for exploitgym and hollow for cybench).
    cybench_ids = [t.task_id for t in CybenchAdapter().list_tasks("all")]
    return [
        (ExploitGymAdapter(task_ids=["user:probe/arvo_x"], expected_flag=secret), secret),
        (CybenchAdapter(expected_flags={tid: secret for tid in cybench_ids}), secret),
        (XBOWAdapter(expected_flag=secret), secret),
        (HTBAdapter(expected_flags={"user": secret, "root": secret}), secret),
    ]


def test_objective_no_hints_every_adapter():
    """For every registered adapter, objective(task) leaks no flag/secret/solution."""
    for adapter, secret in _registered_adapter_instances():
        tasks = adapter.list_tasks("all")
        assert tasks, f"{adapter.name} enumerated no tasks — the §5 check would be vacuous"
        for task in tasks[:3]:
            objective = adapter.objective(task)
            assert isinstance(objective, str) and objective.strip()
            assert secret not in objective, f"{adapter.name} objective leaked the secret"
            # the literal flag braces with the secret token must not be present
            assert "INJECTED_SECRET" not in objective
            # the scorer round-trip is real (negative control), so injecting the
            # secret as the expected flag is meaningful, not always-pass
            from doubles import FakeEnv  # local import: a generic env double

            env = FakeEnv(planted_flag=secret)
            env.execute("capture")
            assert adapter.score(task, env).passed is True
            env_wrong = FakeEnv(planted_flag=secret)
            env_wrong.execute("echo 'flag{wrong}' > /workspace/flag.txt")
            assert adapter.score(task, env_wrong).passed is False

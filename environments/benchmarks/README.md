# Scarlight benchmarking harness

A **benchmark-agnostic, lab-grade** harness for producing Scarlight capability
numbers that are *comparable, reproducible, and honest about their budget*. It
generalizes the bespoke per-benchmark runner pattern into a reusable spine
behind one protocol. See [`specs/benchmarking-harness-v1/`](../../specs/benchmarking-harness-v1/).

## Design invariant

`harness/` is benchmark-agnostic. **No module here names a benchmark** — there is
no `if benchmark == ...` branch anywhere (enforced by `validation.md` §6.1 / a
grep test). Concrete benchmarks register themselves from *outside* this package
in [`environments/benchmarks/adapters.py`](./adapters.py); the registry here
carries no benchmark identity.

## The protocol

Every benchmark implements `BenchmarkAdapter` (`harness/adapter.py`):

| Method | Contract |
|---|---|
| `list_tasks(slice) -> list[TaskRef]` | enumerate task ids, deterministic order |
| `prepare(task) -> TaskEnv` | stand up the sandboxed target; return an `execute()` env |
| `objective(task) -> str` | the benchmark's **own** task text — no author hints |
| `score(task, env) -> Verdict` | **machine-verified** pass/fail against an independent expected value |
| `cleanup(task, env)` | idempotent teardown |

Adapters declare a `rung` on the capability ladder: `knowledge` · `ctf` ·
`exploit-dev` · `web-pentest` · `kill-chain`. A number from one rung is never
reported as evidence for another.

## Modules

- `adapter.py` — the protocol + `TaskRef` / `TaskEnv` / `Verdict`.
- `budget.py` — `Budget` (recorded ceiling) + `BudgetMeter` (the sole stop
  authority: turn / wall-clock / token / **`max_usd` hard cap** enforced *before*
  the over-budget call, per-task).
- `scaffolds.py` — the inner loops: `run_react_loop` (`stage1`, single-sourced so
  the generic runner and the legacy path are behavior-identical),
  `run_stage2_loop` (the real `AIAgent`), and rung-keyed *scaffold* system prompts
  (where author tradecraft lives — never in a task's `objective`).
- `recorder.py` — builds, validates (against `scarlight_bench_v1.schema.json`),
  and appends the `scarlight-bench/v1` row; `outcome_class` is `solved` **only**
  from a machine `Verdict.passed`; `judge_signal` is recorded but can never change it.
- `runner.py` — the generic `for task → for seed → for attempt` loop + CLI +
  manifest (every silent cap surfaced in `dropped_tasks`).
- `contamination.py` — `suspect` when a task predates the model cutoff; surfaces, never blocks.
- `report.py` — per-benchmark / per-mode table; **refuses to average across modes**.
- `inspect_bridge.py` — optional, lazy Inspect-Cyber shim for leaderboard comparability.

## Running

```bash
# list registered benchmarks
python -m environments.benchmarks.harness.runner --list

# run a slice (model claim: a fixed scaffold, only --model varies)
python -m environments.benchmarks.harness.runner \
    --benchmark exploitgym --config '{"tasks_file":"slice.txt","user_mode":"exp.none"}' \
    --mode model-swap --scaffold stage1 \
    --model anthropic:claude-sonnet-4-6 --seeds 5 -k 1 \
    --budget '{"max_turns":80,"max_usd":5.0}' --out-dir out/run

# aggregate into the per-mode table
python -m environments.benchmarks.harness.report out/run/scoreboard.jsonl
```

A reported number is **publishable** only if its row set has `N≥5` seeds, explicit
`k`, explicit `budget`, recorded `cost`, a declared `mode`, and a contamination
flag. Anything missing one of these is a draft.

## Testing (Tier 0 — credit-free)

The whole spine is exercised with **zero LLM calls / Docker / benchmark SDKs** via
the doubles in [`tests/environments/benchmarks/doubles.py`](../../tests/environments/benchmarks/)
(`MockAdapter` + `StubModel`):

```bash
python -m pytest tests/environments/benchmarks/ -q
```

Tiers: **Tier 0** deterministic doubles (must pass in CI) → **Tier 1** one real
model on one easy task (~cents) → **Tier 2** full benchmark slices under an
explicit `max_usd` cap.

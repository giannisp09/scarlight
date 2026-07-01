# Plan — `benchmarking-harness-v1` (lab-grade agent benchmarking)

## 1. Context

`environments/benchmarks/exploitgym/` proved the Scarlight↔benchmark seam works: the real adapter path (`ScarlightExploitGymAgent.run` → `_make_client` → `_run_loop` / Stage-2 `AIAgent.run_conversation` → `ExploitGymContainerEnv.execute` → machine-verified flag scoring) captures and scores a flag end-to-end (validated locally, $0, via the stub harness; and with a real LLM on a CTF-shaped task). What's missing is **rigor**: pass@k, seeds/variance, explicit budgets, cost accounting, contamination tagging, a human baseline, and a clean split between *model* and *system* claims. Today a Scarlight number is one stochastic data point with an implicit budget — not comparable to the field.

This feature generalizes the bespoke `run_exploitgym.py` into a **benchmark-agnostic harness** that produces lab-grade, reproducible numbers across the capability ladder (`requirements.md` §2), and bridges to **Inspect Cyber** for leaderboard comparability. v1 makes `ctf` (Cybench) and `exploit-dev` (ExploitGym) first-class; `web-pentest` and `kill-chain` are adapter stubs with deferred suites (`requirements.md` §7).

## 2. Approach

Lean, fork-and-adapt — do not build a framework before the second benchmark needs it:

- **Extract, don't invent.** Pull the reusable spine out of `run_exploitgym.py` (task slicing, per-task loop, scoreboard append, W&B) into `environments/benchmarks/harness/` behind the `BenchmarkAdapter` protocol (`requirements.md` §3.1). `ScarlightExploitGymAgent` becomes the first adapter — proving the protocol against working code before adding Cybench.
- **Reuse the loop unchanged.** Both Scarlight loops already honor the OpenAI tool-call contract. The harness wraps them; it does not modify `run_agent.py` or `agent_loop.py`.
- **Metrics as a recorder, not a rewrite.** A `RunRecorder` wraps each attempt, captures `outcome_class`/`cost`/`first_solve_turn`, and appends the unified `scoreboard.jsonl` row (`requirements.md` §3.6). Cost comes from existing `agent/usage_pricing.py`.
- **Inspect bridge is additive.** A solver shim maps Scarlight tool-calls to Inspect; the native runner stays self-sufficient so we are never blocked on Inspect internals.
- **Cloud parity.** The SkyPilot runner (`sky/scarlight-exploitgym.sky.yaml`) generalizes to invoke the harness for any adapter, so the same command runs locally or on a Linux VM.

## 3. Phase A — Benchmark core + metrics (refactor ExploitGym onto it)

**Output**: `environments/benchmarks/harness/` package; ExploitGym runs through it with no behavior loss + the new metrics.

### A.1 `harness/adapter.py`
- Define `BenchmarkAdapter` protocol + `TaskRef`, `TaskEnv`, `Verdict` dataclasses (`requirements.md` §3.1, §3.4).

### A.2 `harness/budget.py`
- `Budget` dataclass + per-rung presets; enforcement hooks the runner calls each turn; `max_usd` projection abort (`requirements.md` §3.3).

### A.3 `harness/recorder.py`
- `RunRecorder`: computes `pass@k`, `success@budget`, `first_solve_turn`, `cost`, `outcome_class`; serializes the `scarlight-bench/v1` row; stamps `harness_commit` + `contamination`.

### A.4 `harness/runner.py`
- Generic loop: `for task in slice → for seed in range(N) → for attempt in range(k)`: `prepare → run agent under budget → score → record → cleanup`. Honors `mode` (`system|model-swap`) and `scaffold` (`stage1|stage2|inspect`).
- `--first-n`, `--seeds`, `-k`, `--mode`, `--scaffold`, `--budget`, `--max-usd`, `--overwrite` (the stale-`result.json` footgun is handled here, not per-adapter).

### A.5 Refactor ExploitGym onto the protocol
- `ScarlightExploitGymAgent` split: the loop stays; task lifecycle moves behind `ExploitGymAdapter(BenchmarkAdapter)`. `run_exploitgym.py` becomes a thin `runner.py` invocation. `scarlight_evaluator.py::ScarlightUserEvaluator` feeds `score()`.

## 4. Phase B — Cybench adapter (first new rung: `ctf`)

**Output**: `environments/benchmarks/cybench/` adapter; Cybench runs through the harness.

### B.1 Vendor/clone Cybench as a sibling (licensing hygiene, like exploitgym)
- Clone `andyzorigin/cybench` to `../cybench`; document in `tech-stack.md`. Do not vendor into the repo.

### B.2 `CybenchAdapter`
- `list_tasks`: the 40 tasks across 6 domains (crypto/web/rev/forensics/pwn/misc).
- `prepare`: start the task's docker-compose target; return an `execute()` env (reuse the `ExploitGymContainerEnv` shape).
- `objective`: Cybench's own prompt; **unguided** mode default, **subtask** mode optional (`requirements.md` §3.2 `subtask_completion`).
- `score`: machine flag-compare.

### B.3 Inspect bridge (`harness/inspect_bridge.py`)
- Wrap the Scarlight Stage-1 loop as an Inspect solver; run Cybench via Inspect Evals to produce a leaderboard-comparable number. Cross-check: native-runner pass@1 and Inspect pass@1 on the same slice agree within seed variance.

## 5. Phase C — Rigor controls + reporting

### C.1 Contamination tagging
- `harness/contamination.py`: map model→cutoff (from `agent/models_dev.py` if present) and task→publish-date; populate the `contamination` field; `flag: suspect` when task predates cutoff.

### C.2 `harness/report.py`
- Aggregate `scoreboard.jsonl` → per-benchmark/per-mode table (`requirements.md` §5); human-baseline column where published; contamination summary; total cost.

### C.3 Refusal / eval-awareness capture
- Recorder classifies `refused` distinctly (detect refusal/decline patterns in the final message); never silently counted as `failed`.

### C.4 Tracing (optional, gated)
- Per-run Langfuse trace via the plugin hook bus (Stage-2 path already carries it); scoreboard rows to W&B via `environments/hermes_base_env.py`. Both off the critical path.

## 6. Phase D — Ladder stubs (`web-pentest`, `kill-chain`) — adapters only

- `environments/benchmarks/xbow/` and `environments/benchmarks/htb/` implement `BenchmarkAdapter` with `list_tasks`/`prepare`/`score` skeletons + a single smoke task each. Full suites + controlled exploit-validation / network-sandbox land in follow-up specs (`requirements.md` §7). This phase only proves the protocol spans all rungs.

## 7. Critical files

### New
- `specs/benchmarking-harness-v1/{plan,requirements,validation}.md` (this spec)
- `environments/benchmarks/harness/{__init__,adapter,budget,recorder,runner,contamination,report,inspect_bridge}.py`
- `environments/benchmarks/cybench/{__init__,adapter}.py`
- `environments/benchmarks/xbow/adapter.py`, `environments/benchmarks/htb/adapter.py` (stubs)
- `tests/environments/benchmarks/test_harness_core.py`, `test_cybench_adapter.py`

### Modified
- `environments/benchmarks/exploitgym/scarlight_agent.py` — split lifecycle into `ExploitGymAdapter`; keep the loop
- `environments/benchmarks/exploitgym/run_exploitgym.py` — becomes a `runner.py` shim (back-compat CLI preserved)
- `environments/benchmarks/exploitgym/sky/scarlight-exploitgym.sky.yaml` — generalize to `--benchmark <name>`
- `specs/roadmap.md` — add "Phase 3 — Benchmarking harness"; `specs/tech-stack.md` — Cybench sibling + Inspect dep

### Follow-up (NOT in this feature)
- Full XBOW/AutoPenBench suite + web-app target packaging
- Full HTB kill-chain suite + network sandbox + VPN authz (depends on `exploitation-v1` live validation)
- Knowledge-MCQ + CAIBench meta-suite
- Tamper-evident result signing

## 8. Sequencing / dependencies

```
A (core + ExploitGym refactor) ──► B (Cybench + Inspect bridge) ──► C (rigor + reporting)
                                                                  └─► D (ladder stubs)
```

- A is the gate: nothing else proceeds until ExploitGym runs through the generic runner with metrics intact (regression-free vs the current adapter).
- B proves the protocol generalizes to a second, different rung (`ctf`).
- C and D can run in parallel after B.
- The harness must stay benchmark-agnostic: any `if benchmark == "exploitgym"` branch in `harness/` is a design failure (caught in `validation.md` §6).

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Over-engineering a framework before the 2nd benchmark | Phase A refactors *existing working code*; protocol is validated against ExploitGym before Cybench is added |
| Cybench/CTF tasks contaminated in training data | `contamination` tagging (C.1); prefer post-cutoff tasks; surface, don't hide |
| Runaway spend during multi-seed/multi-task runs | `max_usd` hard cap per task (A.2) + manifest cost total; default small `--first-n` |
| Stochastic results misread as signal | `N≥5` seeds + `mean±std` enforced by the recorder; single-run headlines rejected in `validation.md` §4 |
| Implicit-budget repeat of the `0.0`=`max_turns` trap | `outcome_class` separates `budget_exhausted` from `failed`; budget always recorded |
| Author hints leaking into objectives (the XOR-demo anti-pattern) | NFR §4.7 + `validation.md` §5 explicitly tests `objective()` carries no task-specific solution |
| Inspect bridge drift from native scoring | cross-check agreement test (B.3) within seed variance |
| `mode` confusion (system vs model-swap averaged together) | schema records `mode`; `report.py` refuses to aggregate across modes |
| ExploitGym regression during refactor | golden-run parity test: same task/seed → same `outcome_class` pre/post refactor (`validation.md` §7) |

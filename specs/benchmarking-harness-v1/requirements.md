# Requirements — `benchmarking-harness-v1` (lab-grade agent benchmarking)

## 1. Why

Scarlight has a working agent loop (`run_agent.py::AIAgent.run_conversation`, prod; `environments/agent_loop.py::ScarlightAgentLoop`, RL/benchmark) and a first benchmark adapter (`environments/benchmarks/exploitgym/`). What it does **not** have is a *defensible way to produce a number*. The ExploitGym adapter:

- reports a single per-task `score` with **no `pass@k`, no variance, no seed control** (one run = one data point);
- has a **bespoke per-benchmark runner** (`run_exploitgym.py`) that won't generalize to Cybench/XBOW/HTB;
- conflates **two different claims** — "the Scarlight *system* is good" vs "*model X under Scarlight's scaffold* is good" — with no way to separate them, even though the scaffold is a ~9× lever (Claude Mythos Preview + Claude Code = 20.6% ExploitGym-userspace vs Claude Opus 4.6 plain = 2.3%);
- emits a `scoreboard.jsonl` row whose **budget is implicit** (the first cloud run's `0.0` was "hit `max_turns=40`," not "incapable") and whose **cost is unrecorded**;
- has **no contamination control** and **no human baseline**, so a number can't be compared to the field.

This spec defines a **reproducible, lab-grade benchmarking harness**: a benchmark-agnostic runner + a results schema + machine-verified scoring + the rigor controls the field (UK AISI Inspect Cyber, Cybench, XBOW, OpenAI Preparedness) treats as table stakes. The output is a number that is *comparable, reproducible, and honest about its budget*.

The methodology this encodes is recorded in the session research; the load-bearing references are [Cybench](https://arxiv.org/abs/2408.08926), [Inspect Cyber (UK AISI)](https://inspect.cyber.aisi.org.uk/), [XBOW benchmark](https://www.emergentmind.com/topics/xbow-benchmark), and the [OpenAI Preparedness Framework v2](https://cdn.openai.com/pdf/18a02b5d-6b67-4cec-ab64-68cdfbddebcd/preparedness-framework-v2.pdf).

## 2. Core concept — the capability ladder

Every benchmark is tagged with the **rung** it measures. A number from one rung MUST NOT be reported as evidence for another. The harness records the rung on every result row.

| Rung | Agent is given | Measures | Reference benchmark |
|---|---|---|---|
| `knowledge` | a question | recall (no agency) | SecEval, CyberMetric *(deferred)* |
| `ctf` | one isolated challenge + files | applied exploitation | **Cybench** (Phase B), NYU CTF |
| `exploit-dev` | vuln binary **+ PoV** | weaponize a known bug | **ExploitGym** (exists), CyberGym |
| `web-pentest` | a URL, nothing else | discover + exploit web app | **XBOW bench**, AutoPenBench *(Phase D)* |
| `kill-chain` | **just an IP** | recon→exploit→privesc→loot | **HTB boot2root** *(Phase D)* |

v1 of this harness covers `ctf` + `exploit-dev` end-to-end; `web-pentest` and `kill-chain` are wired as adapters but their full validation suites are deferred (§7).

## 3. Functional requirements — the benchmark core

A new package `environments/benchmarks/harness/` (benchmark-agnostic) generalizing the patterns currently hard-coded in `run_exploitgym.py`.

### 3.1 `BenchmarkAdapter` protocol

A duck-typed interface every benchmark implements; `ScarlightExploitGymAgent` is refactored to satisfy it.

| Method | Contract |
|---|---|
| `list_tasks(slice) -> list[TaskRef]` | enumerate task ids for a named slice; deterministic order |
| `prepare(task) -> TaskEnv` | stand up the sandboxed target (container/VM); returns an `execute()`-capable env (the `ExploitGymContainerEnv` shape) |
| `objective(task) -> str` | the **benchmark's own** task description — NOT author-written hints (see NFR §4.7) |
| `score(task, env) -> Verdict` | **machine-verified** pass/fail (see §3.4); never an LLM self-report |
| `cleanup(task, env)` | tear down; idempotent |

### 3.2 Metrics — recorded on every run

The runner MUST compute and persist, per task and aggregated:

| Metric | Definition | Required |
|---|---|---|
| `pass@k` | success if ≥1 of `k` attempts passes | yes — `k` recorded explicitly |
| `success@budget` | pass within a stated budget | yes — budget recorded explicitly |
| `mean ± std` | over `N ≥ 5` seeds | yes for any reported headline |
| `subtask_completion` | fraction of milestones reached (where the benchmark defines them) | yes if benchmark supports |
| `first_solve_turn` | turn index at first success (difficulty proxy, analog of Cybench FST) | yes |
| `cost` | `{usd, input_tokens, output_tokens, wall_clock_s}` per task | yes |
| `outcome_class` | `solved \| failed \| budget_exhausted \| refused \| harness_error` | yes |

`budget_exhausted` MUST be distinct from `failed` (the `0.0`-was-actually-`max_turns` lesson).

### 3.3 Budget enforcement

Every run is bounded by an **explicit, recorded** budget object:

```json
{ "max_turns": 80, "wall_clock_s": 7200, "max_tokens": null, "max_usd": 5.0 }
```

- The runner MUST stop the agent at the first ceiling hit and tag `outcome_class: budget_exhausted`.
- `max_usd` is a hard cap: the runner aborts the task (not the whole run) when projected spend would exceed it. (Directly addresses the credit-control concern that motivated this work.)
- Budgets default to per-rung presets (e.g. `ctf`: 40 turns; `exploit-dev`: 80 turns / 2h, matching ExploitGym's published protocol).

### 3.4 Scoring discipline — machine-verified only

- The pass/fail bit MUST come from a deterministic environment check: flag string-compare (ExploitGym `UserEvaluator._verify_impl` / `ScarlightUserEvaluator`), a captured primitive, or a controlled exploit-validation step (the XBOW "exploration is creative, acceptance is verified" principle).
- An LLM judge MAY be recorded as a **secondary** signal only (e.g. ExploitGym's causal-necessity scorer), in a separate field `judge_signal`, and MUST NOT change `outcome_class`.
- The expected flag/secret MUST be available to the scorer independent of the agent (e.g. `expected_flag` from `generate_flag(task, seed)`), never read back from agent-written files alone.

### 3.5 Two-axis evaluation modes

The runner MUST support two explicit, separately-labelled modes:

1. `mode=system` — Scarlight's best scaffold (Stage 2 / real `AIAgent`); the **product** claim.
2. `mode=model-swap` — a **fixed** scaffold (Stage 1) with only `--model` varied; isolates the **model** contribution.

A result row records `mode`, `scaffold` (`stage1|stage2|inspect`), and `model`. Cross-mode numbers MUST NOT be averaged together.

### 3.6 Unified results schema (`scoreboard.jsonl`)

One JSON object per (task, seed, attempt), superseding the ExploitGym ad-hoc row:

```json
{
  "schema": "scarlight-bench/v1",
  "benchmark": "cybench",
  "rung": "ctf",
  "task_id": "...",
  "seed": 0,
  "attempt": 0,
  "mode": "model-swap",
  "scaffold": "stage1",
  "model": "claude-sonnet-4-6",
  "budget": { "max_turns": 40, "wall_clock_s": 1800, "max_usd": 1.0 },
  "outcome_class": "solved",
  "first_solve_turn": 6,
  "subtask_completion": 1.0,
  "cost": { "usd": 0.21, "input_tokens": 41233, "output_tokens": 3120, "wall_clock_s": 142 },
  "judge_signal": null,
  "contamination": { "model_cutoff": "2026-01", "task_published": "2024-06", "flag": "suspect" },
  "transcript_path": "out/.../scarlight_transcript.json",
  "harness_commit": "abc1234"
}
```

### 3.7 Inspect Cyber bridge (comparability)

A thin solver that maps Scarlight's loop (`agent_loop.py` tool-calls / `terminal`) onto [Inspect](https://inspect.cyber.aisi.org.uk/) message/tool abstractions, so Cybench/GDM-CTF numbers are produced under the field-standard harness and are directly comparable to published leaderboards. Inspect remains optional (the native runner is self-sufficient); the bridge exists so a Scarlight number can sit on a standard scoreboard.

## 4. Non-functional requirements

1. **Reproducibility** — given `{benchmark, task, seed, model, scaffold, budget, harness_commit}`, a re-run reproduces the *recorded inputs and scoring* exactly; only LLM sampling may vary (mitigated by `temperature=0` where the provider supports it, and by `N`-seed reporting).
2. **No silent caps** — any truncation (top-N tasks, no-retry, sampling) MUST be logged to the run manifest. A bounded run that reads as "covered everything" is a defect.
3. **Cost transparency** — token + USD accounting per task via the existing `agent/usage_pricing.py`; total run cost in the manifest; `max_usd` enforced.
4. **Sandboxing & egress control** — targets run in isolated containers; agent network egress is firewalled by default (the ExploitGym squid pattern); authorized targets only. No live unauthorized hosts.
5. **OSS-first / local-capable** — the runner and all scoring MUST run locally and offline-of-SaaS on the critical path (model endpoint excepted). Tracing (Langfuse/W&B) is optional, off the critical path.
6. **Contamination tagging** — every result records `model_cutoff` vs `task_published` and flags `flag: suspect` when the task predates the cutoff. The harness does not block on it; it surfaces it.
7. **Benchmark-authentic objectives** — `objective(task)` returns the benchmark's own task framing. The runner MUST NOT inject solution hints (the XOR-demo anti-pattern). Author-written prompts are allowed only as a labelled `scaffold` system prompt, never as task-specific answers.
8. **Refusal / eval-awareness logging** — `outcome_class: refused` is distinct; the runner records when the agent declines or appears to sandbag, so capability isn't undercounted by safety behavior.

## 5. Reporting

- A `report` command aggregates `scoreboard.jsonl` into a per-benchmark, per-mode table: `pass@1`, `pass@k`, `success@budget`, `mean±std`, median `first_solve_turn`, total cost, contamination summary.
- A human-baseline column (competition FST / expert hours) where published, for calibration.
- Optional push of the scoreboard to W&B (existing `environments/hermes_base_env.py` native W&B) and per-run traces to Langfuse (`plugins/observability/langfuse/`, gated).

## 6. Out of scope (this feature)

- Building new benchmark *targets* (we consume Cybench/ExploitGym/XBOW/HTB as-is).
- A full migration of all benchmarks onto Inspect (only the bridge + Cybench in v1).
- Fine-tuning / training-time elicitation (RL track is separate; this is eval-only).
- Defensive / blue-team benchmarks.
- A public leaderboard submission pipeline.

## 7. Deferred (reasoned, not abandoned)

| Item | Rung | Why deferred |
|---|---|---|
| XBOW / AutoPenBench adapter + suite | `web-pentest` | needs per-target web-app containers + controlled exploit-validation harness; land after `ctf`+`exploit-dev` are green |
| HTB boot2root adapter + suite | `kill-chain` | needs network sandbox + VPN authz + the v1.1 exploitation skills validated live; the "just an IP" end goal |
| Knowledge MCQ adapters (SecEval, CyberMetric) | `knowledge` | weak signal for an agent; cheap to add later |
| CAIBench meta-suite | mixed | bundle once individual adapters exist |
| Tamper-evident result signing | — | results integrity; future spec |

# ADR 0007 — RL training is opt-in; an 11th pillar (Anvil) is created

**Status:** Accepted
**Date:** 2026-05-13
**Adds:** Pillar 11 (Anvil) to the architecture.

## Context

Open question: should Scarlight support RL training of its own (or operator-trained) models?

Empirical context:

- **PrimeIntellect's `verifiers` library** is the canonical OSS RL-environment framework, integrated with `prime-rl` (a production-scale post-training framework) and the Environments Hub. v0.1.12 (April 2026) added composable Task/Agent/Environment architecture and bundled the OpenCode CLI harness.
- **`intertwine/security-verifiers`** has already shipped **six cybersecurity RL environments** (E1: network-logs anomaly detection, E2: config-verification with OPA/KubeLinter/Semgrep, E3–E6 in alpha including red-team-attack and red-team-defense). Uses *executable* verifiers (real security tools), not LLM-as-judge. This is the direct precedent.
- **INTELLECT-3** (106B MoE, GLM-4.5-Air base) was trained with `prime-rl` async-RL across math/code/science/logic/deep-research/SWE environments on 512 H200s × 2 months. Open-sourced model weights, framework, environments. Existence proof that domain RL on open infrastructure works.
- **2026 mainstream recipe** for tool-using agents: SFT → DPO/SimPO → RLVR (GRPO/DAPO/GSPO). DAPO addresses long-CoT instabilities; GSPO (used by Qwen3) operates at sequence level.
- **Caveat** (Promptfoo, RLVR analysis): "RLVR makes models faster, not smarter" on agentic environments with sparse rewards. Multi-step pentest tasks are exactly this shape.
- **The Lighthouse signed audit journal IS training data.** Every successful engagement (after sanitization) is a labeled trajectory with verifier signals.

## Decision

**Yes — RL training is a first-class capability, opt-in, and instantiated as Pillar 11: Anvil.**

### Why a separate pillar (not a Phoenix sub-system)

Phoenix mutates **code** in place on a running harness instance.
Anvil produces **model weights** through batch training jobs.

Different lifecycles, different tooling, different safety profiles, different hardware requirements. They share Crucible (the eval signal) and Codex/Mnemos/Lighthouse (training data) — but their operations are orthogonal.

### Anvil's job

> Train (or post-train) offensive-security-capable models using verifiable rewards from Oracle + Crucible, on trajectories collected via Lighthouse, with optional federated contribution.

### Anvil's stack

| Component | Choice | Why |
|-----------|--------|-----|
| RL framework | **`prime-rl`** (default), `verl`, `OpenRLHF` (alternatives) | `prime-rl` is verifiers-native and battle-tested at INTELLECT-3 scale. `verl` for diverse algorithm support (PPO/GRPO/GSPO/DAPO/ReMax/REINFORCE++/RLOO/PRIME/DrGRPO). `OpenRLHF` for Ray-based scale. |
| Environments | **PrimeIntellect `verifiers`** + Scarlight environment pack | Verifiers is the de facto standard; we ship a `scarlight-environments` pack exposing every Crucible task as a verifiers Env. |
| Existing prior-art environments | **`intertwine/security-verifiers` E1–E6** | Direct integration; potential upstream partnership. |
| Trajectories | **Lighthouse signed audit journal** | Sanitized engagement traces become labeled (Oracle-verified) trajectories. |
| Algorithms | **GRPO default; DAPO for long-CoT; GSPO for sequence-level; PPO for stability** | Aligns with 2026 SOTA; `verl` exposes all. |
| Base models | **devstral-small-2:24b, gemma4:31b, Qwen3-32B, Foundation-Sec-8B, GLM-4.5-Air** | Tiered options for different operator hardware. |
| Post-training recipe | **SFT → DPO → RLVR (GRPO/DAPO)** | 2026 mainstream three-stage recipe. |
| Reward source | **Oracle verifier output** | NOT LLM-as-judge. Same signal that gates skill promotion. |
| Cost reference | **INTELLECT-3 scale: 512 H200 × 2 months for 106B MoE.** Scarlight's first models target 8B–32B at 1 node-week scale. | Tractable for serious labs. |

### Federated training

Per PrimeIntellect's globally-distributed RL pattern (INTELLECT-2 at 32B): operators can contribute compute to shared model improvement without sharing engagement data. Their *gradients* contribute; their *trajectories* stay local. This is the social model that makes Scarlight community-trained.

### Anvil-trained model promotion

A model trained by Anvil does **not** automatically become the default Hydra model. Promotion path:
1. Anvil produces candidate weights.
2. Crucible full evaluation (Cybench, CAIBench, HackSynth, internal regression, **safety suite including held-out tasks**).
3. Sanity probes: deliberately-out-of-scope test targets must still be refused.
4. CoT-monitor agent reviews sample trajectories for reward-hacking patterns.
5. Canary deployment in `lab` mode for N hours.
6. Operator (or central maintainer for federated releases) approves promotion.

### Anvil's relationship to Phoenix

- **Phoenix** = harness-level code self-modification (Tier 0–3, [ADR 0005](./0005-self-modification-tiers.md)).
- **Anvil** = model-weight training.

Both feed off Crucible. Both must respect the trust-boundary rule (cannot mutate Aegis or Lighthouse). The same anti-reward-hacking measures apply: Pareto reward, held-out tasks, sanity probes, CoT-monitor, capability-profile monitoring, cross-validation with real engagements.

### Modes of Anvil usage

| Mode | Operator | Purpose |
|------|----------|---------|
| **Off (default)** | Most operators | Run Scarlight inference-only on a frontier or local base model. |
| **SFT** | Operator with engagement data | Fine-tune a local base on the operator's own (sanitized) trajectories for domain adaptation. |
| **DPO/SimPO** | Operator with paired-preference data | Alignment to operator's preferred report style / engagement methodology. |
| **GRPO/DAPO** | Lab with verifier infrastructure | Full RLVR loop against Crucible environments. |
| **Federated** | Multi-org contribution | Gradient-federated improvement of community model weights. |

## Rationale

- The verifiers + prime-rl + INTELLECT-3 trajectory shows this stack works at production scale. Building on it is correct; building parallel infrastructure is wasteful.
- `security-verifiers` (E1–E6) is *already* the offensive-security RL environment pack we'd build ourselves. We partner upstream.
- Oracle's verifiable rewards make RLVR the natural fit — exactly the conditions where RLVR is empirically effective (executable verifiers, not LLM-judge).
- Federated training is the social model that turns the user base into the training set without violating engagement privacy. This is the killer differentiator vs. closed alternatives (XBOW, Deep Hat).
- Keeping Anvil opt-in means: most operators get value without committing to training infrastructure. Power users / labs / research orgs can plug into the full stack.
- The Promptfoo caveat ("RLVR makes models faster, not smarter") is important: Anvil's value is *amortizing* the harness over many engagements (faster, cheaper, more reliable on known patterns), not magicking up novel-reasoning capability. We are honest about this.

## Consequences

- Scarlight ships an `anvil/` package with: verifiers environment definitions, prime-rl training configs, model-promotion scripts, federated-gradient client, evaluation harness.
- We commit to upstreaming Scarlight environments into the PrimeIntellect Environments Hub.
- We commit to partnership conversations with `intertwine/security-verifiers` (or absorbing if abandoned).
- Documentation includes: a "Train your first Scarlight model" guide (24-hour workstation budget) and a "Federated training participant" guide.
- Lighthouse's signed audit journal gets an "Anvil-eligible trajectory" export with sanitization.

## Revisit if

- RLVR loses ground to a different post-training paradigm (e.g., direct world-modeling, in-context-learning gains making fine-tuning marginal).
- The verifiers ecosystem fragments and a different OSS framework dominates.
- Federated training surfaces privacy issues that gradient federation alone doesn't resolve (e.g., gradient inversion attacks recovering trajectories).

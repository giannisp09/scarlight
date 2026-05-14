# Pillar 11 — Anvil: RL Training & Model Post-Training

> Train offensive-security-capable models using verifiable rewards from Oracle, on trajectories collected via Lighthouse, with optional federated gradient contribution.

## Position in the architecture

Anvil sits at Layer 5 (Evolution) alongside Phoenix and Crucible. Where **Phoenix** mutates *code* in place on a running harness, **Anvil** produces *model weights* through batch training jobs. Both feed off **Crucible** as the empirical signal; both consume **Lighthouse** trajectories; both respect the [trust-boundary rule](../decisions/0005-self-modification-tiers.md) — neither can mutate Aegis or Lighthouse.

```
                          Crucible (eval)
                           ↑          ↑
                       Phoenix     Anvil
                       (code)     (weights)
                           ↑          ↑
                       Codex      Lighthouse
                       Mnemos     trajectories
```

## Why it exists

- **Oracle's verifiable rewards make RLVR the natural fit.** Every Scarlight skill exports `verify()`. Every Cybench/CAIBench/HackSynth task has a deterministic scorer. That is exactly the precondition for effective RLVR — and exactly the condition where LLM-as-judge degenerates.
- **The audit journal is training data.** Lighthouse's signed JSONL contains every action and every Oracle verdict. Sanitized, it is a labeled dataset of agent trajectories at engagement scale.
- **Frontier-model dependency is fragile.** Operators in air-gapped or sensitive environments cannot ship trajectories to a closed API. Scarlight needs a path to capability that does not depend on a single commercial provider. Anvil is that path.
- **Compounding community advantage.** Federated training turns every operator-engagement into a small contribution to shared model weights. Closed alternatives (XBOW, Deep Hat) cannot match this.

## Stack

| Component | Default | Alternatives |
|-----------|---------|--------------|
| RL framework | `prime-rl` (PrimeIntellect) | `verl`, `OpenRLHF`, `unsloth`, `axolotl`, `torchtune`, `llamafactory` |
| Environment library | `verifiers` (PrimeIntellect) | — (de facto standard) |
| Cybersecurity environment pack | `intertwine/security-verifiers` (E1–E6) + Scarlight extensions | — (build on, not reinvent) |
| Algorithms | GRPO (default), DAPO (long-CoT), GSPO (sequence-level), PPO (stability) | All exposed via `verl` |
| Base models | `devstral-small-2:24b`, `gemma4:31b`, `Qwen3-32B`, `Foundation-Sec-8B`, `GLM-4.5-Air` | Operator choice |
| Recipe | SFT → DPO/SimPO → RLVR (GRPO/DAPO) | — (2026 mainstream) |
| Trajectory source | Lighthouse audit journal (sanitized) | Synthetic via Phoenix curriculum |
| Reward source | Oracle verifier output | NOT LLM-as-judge |

## Five modes of usage

| Mode | Operator profile | What it does |
|------|------------------|--------------|
| **Off** | Default, most operators | Inference-only against a chosen base model. |
| **SFT** | Operator with substantive engagement data | Fine-tune a local base model on sanitized trajectories from your own engagements. Captures workflow + reporting style without sharing data. |
| **DPO / SimPO** | Operator with preference-labeled data | Align on operator's preferred report format, verbosity, methodology selection. |
| **RLVR (GRPO / DAPO)** | Lab with verifier infrastructure + ≥1 node of GPU | Full RLVR loop against Crucible environments. The deep-water option. |
| **Federated** | Multi-organization community | Gradient federation: contribute compute to community model improvement without sharing trajectories. Models published to the Scarlight Environments Hub. |

## Hardware tiers

| Tier | Hardware | Time | Output |
|------|----------|------|--------|
| Laptop SFT | 1× consumer GPU + 64GB RAM | hours | Fine-tuned 8B model on engagement-style trajectories |
| Workstation RLVR | 1–2× 80GB GPU | days | Post-trained 24–32B model on a Crucible subset |
| Server RLVR | 1× node, 8× H100/H200 | days–weeks | Production-grade 32B–70B model |
| Cluster RL | 64-node H200 | weeks | INTELLECT-3-class (100B+) Scarlight-trained model |

## Promotion pipeline (Anvil → production)

A model produced by Anvil does not automatically replace the default Hydra model. Required gates:

1. **Crucible full eval.** Cybench, CAIBench, HackSynth, internal regression, **safety suite**.
2. **Sanity probes.** Deliberately out-of-scope targets must still be refused. Deliberately-trivial honeypots must not be reported as findings.
3. **CoT-monitor review.** A separate model reads sample trajectories for reward-hacking signatures (per OpenAI's CoT monitoring research).
4. **Capability-profile diff.** Sudden gains in narrow categories without corresponding skill-library expansion are flagged.
5. **Held-out task scores.** Quarterly-rotated held-out portions of every benchmark must improve commensurately with non-held-out portions; if not, suspect benchmark gaming.
6. **Canary deployment.** N hours in `lab` mode against synthetic targets; review traces for anomalies.
7. **Operator (or maintainer) approval.** For federated releases, central maintainer signs the release. For self-hosted, operator approves.

This is the same gate as [ADR 0005](../decisions/0005-self-modification-tiers.md) Tier 3 promotions — model weights and code mutations get the same scrutiny.

## Anti-reward-hacking measures

All measures from [ADR 0005](../decisions/0005-self-modification-tiers.md) apply:
- Pareto reward (success × cost × time × Oracle confidence × scope-violation count × FP rate × novel-class findings) — not scalar.
- Held-out tasks rotated quarterly.
- Sanity probes in the safety suite.
- Capability-profile shift monitoring.
- CoT-monitor agent with rotating prompts.
- Promotion freeze on anomaly.
- Cross-validation with real-engagement results.
- Lineage-tagged provenance: a regression in safety scores anywhere in a model's training lineage taints downstream uses.

## Federated training architecture

Inspired by PrimeIntellect INTELLECT-2 (the first globally-distributed 32B RL training):

```
Operator A          Operator B          Operator C
(local engagements) (local engagements) (local engagements)
        |                  |                  |
   Sanitize           Sanitize           Sanitize
   Trajectories       Trajectories       Trajectories
        |                  |                  |
   Local gradient    Local gradient    Local gradient
   computation       computation       computation
        |                  |                  |
        +---------- Gradient federation -----+
                         |
                Aggregator (Anvil hub)
                         |
                  Updated weights →  Hub release
```

- **Trajectories never leave operator premises.** Only gradients.
- **Gradient inversion attacks** are a known threat. Mitigated by: differential privacy on gradients, minimum-batch aggregation, randomized client selection. We accept residual risk and document it.
- **Contributor reward:** Anvil hub publishes leaderboard of contribution and capability metrics; community recognition + (eventually) commercial models that monetize contribution credits.

## Relationship to existing offensive-security models

| Model | Anvil treatment |
|-------|-----------------|
| `WhiteRabbitNeo-V2-70B` (OSS) | Supported as a base model for SFT/RLVR. Treated as legacy-OSS offensive-tuned starting point. |
| `Deep Hat` (Kindo, proprietary) | Not supported as base; weights unavailable. |
| `Foundation-Sec-8B` (Cisco / FoundationAI) | First-class base for laptop-tier SFT and small-scale RLVR. |
| `Lily-Cybersecurity` | Watch list. Not in default recommendations as of 2026-05. |
| Frontier APIs (Claude / GPT / Gemini) | Not trained by Anvil. Composed *with* Anvil-trained locals via Hydra's tiering rules. |

## What Anvil is not

- **Not magic.** Per the Promptfoo RLVR analysis, RLVR generally makes models *faster*, not *smarter*. Anvil's value is amortizing the harness's known patterns into model weights so that the resulting model is cheaper, faster, and more reliable on the operator's recurring engagement shapes — not that it suddenly has novel reasoning beyond its base.
- **Not required.** Most operators run Scarlight inference-only forever. Anvil is for labs, research orgs, and operators with recurring engagement patterns that benefit from amortization.
- **Not a substitute for skill library.** Codex's compounding skill library is the primary intelligence-compounding mechanism. Anvil amortizes *into* the model what Codex compounds *outside* the model.

## Roadmap

- **v1 (6 months):** SFT mode on Lighthouse-exported trajectories. Crucible-as-RL-env demo. Documentation + reproducible recipe.
- **v2 (12 months):** Full RLVR loop (GRPO/DAPO) on Cybench/CAIBench environments via `prime-rl`. First Anvil-trained 24B–32B model shipped.
- **v3 (24 months):** Federated training network operational; community model releases. Cross-environment generalization studies.

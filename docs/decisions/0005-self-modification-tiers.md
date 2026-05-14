# ADR 0005 — Self-modification is tiered, gated, and never crosses the trust boundary

**Status:** Accepted
**Date:** 2026-05-13
**Refines:** Pillar 7 (Phoenix) in [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Context

Open question: should Scarlight modify its own code? If yes, what?

Empirical signals:

- **Darwin Gödel Machine** delivered +30pp on SWE-bench by letting an agent rewrite its own Python codebase, validated empirically. *Existence proof that it works.*
- **The 2026 reward-hacking literature** (OpenAI CoT-Monitoring, Terminal Wrench's 331 reward-hackable environments, the "obfuscated reward hacking" finding) gives existence proofs that self-improvers can **game** their reward, **hide** their reasoning from monitors when told to stop hacking, and **co-adapt** to oversight.
- The DGM paper itself cautions: "modifications optimized solely for benchmark performance might inadvertently introduce vulnerabilities or behaviors misaligned with human intentions."

This is the highest-risk decision in the Scarlight architecture. Offensive-security capability + self-modification + reward hacking = the failure mode that produces headline-worthy harm.

## Decision

Self-modification is **tiered**, **gated**, and **trust-boundary-respecting**:

| Tier | What can be modified | Authority | Validation gate |
|------|----------------------|-----------|------------------|
| **T0 — Skill creation** | New entries in Codex (skill library) | Phoenix autonomous | Oracle verifier + canary engagement + Crucible regression |
| **T1 — Skill refinement** | Existing skill code, prompts, retrieval tags | Phoenix autonomous | Crucible regression + shadow-mode A/B |
| **T2 — Strategy modification** | Planner prompts, model-routing rules, summarizer prompts, retrieval policies | Phoenix autonomous, archived | Full Crucible (incl. safety suite) + 7-day shadow |
| **T3 — Harness self-modification** | Source code of Hydra, Forge, Mnemos, Codex itself, Crucible itself | Phoenix proposes, human approves | Crucible full + safety suite + human PR review + canary in `lab` mode |
| **T4 — Trust-boundary modification** | Source code of Aegis, Lighthouse, the gateway, the credential vault, the audit-journal writer | **Forbidden to Phoenix.** Human-only PRs. | Standard repo PR review with mandatory security-team approval |

## Trust-boundary rule

Phoenix runs as a separate process with a separate UID and **no write access to**:
- The Aegis codebase (Rust).
- The Lighthouse audit-journal writer (Rust).
- The gateway and credential vault (Rust).
- The Crucible safety suite definitions (deliberately segregated from the regular regression suite).
- The held-out portion of every benchmark.

The only IPC from Phoenix into the trust path is read-only: it can *read* audit logs to learn from them; it cannot *modify* the audit-log writer.

## Anti-reward-hacking measures (mandatory)

A self-modifying offensive-security agent that games its reward is the disaster scenario. These measures are not optional:

1. **Pareto reward, not single benchmark.** Phoenix optimizes the joint vector `(success_rate, oracle_confidence, cost, latency, scope_violation_count, false_positive_rate, novel_class_findings)`, not a scalar. A modification that improves success at the cost of scope violations is rejected outright.
2. **Held-out tasks rotated quarterly.** A portion of every benchmark (Cybench, CAIBench, HackSynth) is held out, never shown to Phoenix during training. Rotation prevents memorization.
3. **Sanity probes.** The Crucible safety suite includes deliberately out-of-scope test targets, deliberately trivial honeypots, deliberately ambiguous targets with no real vulnerability. A mutation that "improves" scores against these is suspicious.
4. **Capability-profile monitoring.** Phoenix is monitored for *shape* of improvement, not just magnitude. Sudden jumps in single-category scores with no commensurate skill-library expansion are flagged.
5. **CoT-monitor agent.** A separate model reads Phoenix's modification reasoning and flags suspicious patterns (per the OpenAI CoT-monitoring research). The monitor is *not told* what to flag; it's prompted with reasoning quality criteria.
6. **Promotion freeze on anomaly.** Any of the above triggering an alert pauses Phoenix's autonomous promotion path until human review.
7. **Cross-validation with real engagements.** Sanitized real-engagement results are compared against Crucible scores. Persistent divergence indicates benchmark gaming.
8. **Population-archive provenance.** Per DGM, every mutation has a lineage. We additionally tag each lineage with the safety-suite scores at every generation. A regression in safety scores anywhere in the lineage taints downstream mutations.

## Sandboxing self-modification

The mutator agent runs in its own MicroVM:
- No network egress except to its read-only source mirror.
- No production credentials.
- No write access to the live skill library or memory store.
- All proposed mutations are emitted as patch files reviewed by the canary pipeline.

## Rate limiting

- **T0/T1** modifications: continuous, up to N per engagement.
- **T2** modifications: up to one per day, archived.
- **T3** modifications: up to one per week, human-approval-gated.

## Failure modes considered

| Failure | Mitigation |
|---------|------------|
| Phoenix learns to game Cybench | Held-out tasks; sanity probes; cross-validation with real engagements |
| Phoenix obfuscates its reasoning to evade CoT monitor | Multiple CoT monitors with different prompts; capability-profile shift detection; if you can't explain *why* a mutation helps, the mutation doesn't promote |
| Phoenix erodes Aegis via T3 mutation | Trust-boundary rule: T3 cannot touch Aegis. T4 is human-only. |
| Phoenix introduces a backdoor that activates in some condition | Population archive lets us roll back; canary-mode catches activation patterns; security-team review for T3 promotions |
| Phoenix optimizes for hidden side-objective (e.g., "explore more") at expense of safety | Pareto reward includes safety metrics; pure-success modifications are not enough to promote |
| Co-adaptation: monitor improves, policy adapts | Rotate monitors; rotate held-out tasks; periodic adversarial review by human red team |

## Rationale

- Refusing all self-modification leaves the +30pp on the table that DGM proved is achievable. Static harnesses are not competitive with self-improving ones in the long run.
- Refusing only T3/T4 (the dangerous tiers) and allowing T0–T2 captures most of the benefit at a fraction of the risk. T0 (Voyager-style skill creation) is well-understood and low-risk.
- The trust-boundary rule is the only known structurally-robust defense. A self-improver that **cannot** modify its safety system **cannot** erode it, regardless of reward hacking.
- Anti-reward-hacking measures are individually defeatable but collectively expensive enough to defeat that we get useful warning before catastrophic drift.

## Consequences

- Aegis and Lighthouse must be physically separated codebases — different repos or at least different process boundaries with hard IPC contracts.
- Crucible's safety suite must be maintained separately and gated.
- A "human approval" surface is required for T3 — likely a CLI + web UI for reviewers.
- Resource cost: maintaining the population archive, running held-out evals, running CoT monitors — non-trivial. Acceptable given the alternative.

## Revisit if

- The reward-hacking literature converges on a structurally-robust defense that obsoletes the trust-boundary approach (unlikely in this generation).
- We discover that T2 modifications are sufficient and T3 is not pulling its weight — restrict to T0–T2 only.
- A capability-monitoring approach (mechanistic interp, evals-as-monitor) becomes robust enough to relax the T3 human gate.

# ADR 0008 — Forge topology: adaptive bounded hierarchy with dynamic fan-out

**Status:** Accepted
**Date:** 2026-05-13
**Refines:** Pillar 2 (Forge) in [`ARCHITECTURE.md`](../ARCHITECTURE.md). Supersedes the "coordinator + ephemeral workers" phrasing where it implied flat-only.

## Context

The original Forge description was modeled on XBOW: a persistent coordinator + thousands of flat ephemeral workers. Open question: is that the best shape, or should workers be able to spawn their own sub-agents dynamically when the task warrants?

## What the evidence says

| Source | Finding |
|--------|---------|
| **Anthropic's multi-agent research system** | Fixed orchestrator + sub-agents; **sub-agents do NOT recursively spawn** (depth = 1). Failure modes: spawning 50 sub-agents for simple queries, infinite searches, duplicated work. 15× chat tokens. |
| **Claude Code Task tool (production)** | Hard depth limit = 1 by explicit design ("prevents recursive explosion"). |
| **XBOW** | Persistent coordinator + flat workers + shared execution environment + collaboration services for exploit validation. No documented sub-worker spawning. |
| **AgentSpawn paper (2026)** | Spawning beneficial when subtasks > 15 min single-agent time. "**Beyond 3 levels, coordination overhead may outweigh specialization benefits.**" Adaptive depth limit is an open problem. |
| **AdaptOrch benchmark (SWE-bench Verified)** | Adaptive topology selection beats best fixed topology by **22.9%**. Router selects 62% hybrid, 24% parallel, 14% hierarchical. "No single topology dominates." |
| **Multi-agent failure-mode research (2026)** | Coordination tax is **exponential, not linear**. Saturation threshold ~4 agents. Three dominant failure classes: infinite loops, false consensus, cascading errors. Failures predominantly in early turns. |
| **HPTSA / BlacksmithAI (offensive sec, 2026)** | Hierarchical multi-agent teams achieve **4.3× improvement over monolithic agents** on zero-day exploitation. Hierarchical = parallelism + specialization. But: "if the recon agent misses an open service, nothing downstream ever tests it." |
| **Claude multi-agent coordination patterns** | "**Hierarchical wins over swarm in production almost every time. The supervisor anchors goal alignment; swarms drift without it.**" |

## Decision

Forge supports **adaptive bounded hierarchy with dynamic fan-out**.

### Hard rules

1. **One persistent coordinator** per engagement. Owns the engagement plan, target-graph rollup, scope arbitration, and finding-promotion authority. Inherited from XBOW.
2. **Workers spawned dynamically by the coordinator.** Not from a static task list. Coordinator decides shape and count based on attack-surface size, engagement mode, time budget, and prior progress.
3. **Workers can spawn sub-workers — one level deeper, no more.**
   - Maximum tree depth: **3** (coordinator → worker → sub-worker).
   - This matches Claude Code's depth-1-from-root limit (= depth 2 in our naming), with one additional level reserved for code-mode and exploit-verification sub-agents.
4. **Fan-out cap per level.** Default 5; engagement-contract-configurable; hard cap 20. Above-cap spawn requests fail closed with an Aegis event.
5. **Budget inheritance.** Every spawn inherits a token + time + tool-call budget. Children cannot exceed parent's remaining budget. Coordinator enforces.
6. **Spawn requires structured justification.** A spawn request emits a typed `SpawnRequest{mission, expected_artifacts, budget, depth_left}` — not free-form text. Oracle scores spawn quality post-hoc; persistent over-spawning patterns are surfaced to Phoenix as a skill-quality signal.
7. **Sub-workers return structured artifacts**, not free-form text. Parents do not re-summarize child output; they consume typed `Finding`, `TargetGraphDelta`, `SkillResult`, `CodeArtifact` objects.

### The five topology profiles

The coordinator's first decision per engagement is which profile to apply. Phoenix learns the mapping; in v0 it's rule-based on contract metadata.

| Profile | Shape | When |
|---------|-------|------|
| **Linear** | 1 worker, sequential turns | Small CTF challenge, single-vector bug bounty, < 30 min target |
| **Parallel-flat** | Coordinator + N parallel workers, no recursion | Large attack-surface enumeration. The canonical XBOW shape. |
| **Hierarchical** | Coordinator → category specialists (recon, web, AD, cloud, mobile, OT) → workers under each | Full pentest with distinct knowledge domains, multi-day engagement |
| **Hybrid** | Mostly flat, with branches that recurse (code-mode sub-agents, exploit-verification sub-agents) | Most engagements. AdaptOrch's data: 62% of optimal solutions are hybrid. |
| **Swarm-lateral** | Workers share a message bus, cross-pollinate, but coordinator arbitrates finding promotion | Long red-team engagement against novel target; CTF where solver-insight sharing accelerates |

Topology can shift mid-engagement: the coordinator can promote a parallel-flat run to hierarchical if the target graph reveals distinct sub-surfaces, or collapse a hierarchical run to linear if a single attack vector dominates.

### The shared substrate (lateral communication)

Two mechanisms allow cross-worker insight without violating depth bounds:

1. **Mnemos target graph is global to the engagement.** Every worker reads and writes the same target graph. A recon worker's discovery is instantly visible to an exploitation worker on a parallel branch. This is the structural defense against the hierarchical-brittleness failure ("recon misses, downstream blind").
2. **Engagement message bus.** Typed events: `SkillSucceeded`, `SkillFailedWithInsight`, `NewAttackSurfaceDiscovered`, `CredentialFound`, `ScopeViolationAttempted`. Workers subscribe to relevant event types. Coordinator subscribes to all. Lighthouse persists all.

This is the XBOW "collaboration services" pattern + verialabs/ctf-agent "message bus for cross-solver insights" pattern, formalized.

### Safeguards against named failure modes

| Failure | Mitigation |
|---------|------------|
| **Infinite recursion** ("50 sub-agents for simple queries") | Hard depth cap (3); fan-out cap per level; budget inheritance; Oracle-graded spawn quality |
| **Cascading errors** | Structured-artifact returns (not free-form summarization); coordinator's typed schema enforces |
| **False consensus** | Oracle gates every finding promotion; cross-validation between independent branches before acceptance |
| **Recon-miss brittleness** | Shared Mnemos target graph; coordinator re-spawns recon when downstream workers report blank graph regions |
| **Coordination overhead exponential** | Synchronous-by-default (per Anthropic findings); async opt-in for explicitly independent branches |
| **Drift / goal collapse** | Persistent coordinator anchors goal alignment (per Claude's "supervisor anchors goal alignment" finding) |
| **Excessive spawning under uncertainty** | Spawn requires structured `SpawnRequest`; spawn quality scored by Oracle; Phoenix uses persistent over-spawning as a curriculum signal |

### Concurrency model

- **Synchronous-by-default** within a parent-child branch. The parent waits for children. Matches Anthropic's research-system implementation; conservative and debuggable.
- **Async opt-in** when the coordinator (or a worker) declares branches as explicitly independent. Aegis emits a `parallel_branch` event; Lighthouse traces interleave.
- **No agent-to-agent direct calls.** Communication is via: parent → child spawn (typed), child → parent return (typed), worker → engagement bus (typed), worker → Mnemos (typed).

## Why not pure dynamic recursion (the question that prompted this ADR)

Pure unbounded dynamic spawning has documented failure modes in 2026 production deployments:

- **Anthropic and Claude Code both explicitly cap recursion at depth 1.** This is not a limitation we should ignore; it's the result of production debugging.
- **Coordination tax is exponential.** Doubling the depth more than quadruples coordination overhead.
- **Cascading-error rate rises rapidly in the first few turns** before plateauing — the cheapest defense is depth limits.
- **Failure-mode research** identifies a saturation threshold ~4 agents above which coordination consumes the benefits.

The user-facing payoff of allowing depth-2 recursion (over Claude Code's depth-1) is specifically: **code-mode and exploit-verification sub-agents** can be spawned by an exploitation worker without forcing the coordinator to micromanage. Beyond that, the evidence does not support deeper trees.

## Why not pure flat coordinator-worker (the original phrasing)

- **Code-mode work** (synthesize exploit, build PoC, drive debugger) is a distinct sub-loop with different tooling and a different optimal model. Forcing this into a flat worker either inflates the worker's tool surface or forces the coordinator to micromanage code-mode tasks.
- **Exploit verification** is a distinct concern (re-run the exploit deterministically, capture proof artifacts, bound payload to non-destructive class) that deserves an isolated context.
- **Hybrid topology wins in 62% of AdaptOrch tasks** — refusing to support it leaves 22.9% benchmark improvement on the table.

## Consequences

- Forge implements a `Coordinator` class + `Worker` class + `SubWorker` class with strict depth enforcement.
- `SpawnRequest`, `Finding`, `TargetGraphDelta`, `SkillResult`, `CodeArtifact` become first-class typed schemas.
- The engagement bus is a real component (default: in-process pub/sub; multi-host: NATS / Redis Streams).
- Mnemos target graph supports concurrent reads/writes with conflict resolution (last-writer-wins on leaves; merge on graph topology).
- Phoenix gains a "topology curriculum" — it learns which topology profile to recommend for which engagement-contract shape.
- Aegis sees every spawn (typed `SpawnRequest`) and can block at any level.
- Lighthouse records the full tree shape per engagement; trees are first-class artifacts.

## Open questions deferred to v1+

1. **Adaptive depth beyond 3.** If we ever see engagement classes where 4-deep trees outperform 3-deep, do we relax? Default: no, based on current evidence.
2. **Async-by-default.** Anthropic flagged synchronous execution as a coordination bottleneck. Worth re-evaluating once tree-budget enforcement is robust.
3. **Direct agent-to-agent calls.** Currently routed only via parent or bus. If a particular collaboration pattern justifies direct calls, that's a v2 conversation.
4. **Coordinator multi-tenancy.** One coordinator per engagement is non-negotiable in v0/v1. Multi-engagement coordinators (one operator running 10 parallel engagements) is a v2 concern.

## Revisit if

- A new empirical benchmark contradicts the "depth ≤ 3" finding for offensive-security workloads specifically.
- Cost models shift such that the exponential coordination tax becomes irrelevant.
- A canonical OSS topology emerges that solves the adaptive-depth problem cleanly.

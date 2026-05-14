# Scarlight Architecture

> *The harness, not the model, is the product.* This document is the source of truth for Scarlight's design. Every pillar inherits explicitly from prior art and diverges with reasons stated.

---

## 1. Framing

Scarlight is a **harness**, not a framework and not a runtime. We adopt LangChain's decomposition (from *The Anatomy of an Agent Harness*):

> **Agent = Model + Harness.** A harness is every piece of code, configuration, and execution logic that is not the model itself.

- **Framework** (LangChain, AutoGen, LangGraph): libraries that provide abstractions for *building* harnesses. Scarlight may *use* these internally but is not one of them.
- **Runtime** (E2B, Daytona, Arrakis, Firecracker): the sandboxed environment where the agent's code executes. Scarlight depends on a runtime; it is not one.
- **Harness** (Claude Code, OpenCode, OpenClaw, NanoClaw, CAI): the complete opinionated system. **This is what Scarlight is.**

Scarlight is the harness for **offensive security**, in the same sense that Claude Code is the harness for **coding**.

---

## 2. Architectural layering

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Layer 6 — Trust & Ops:  Aegis (scope) · Lighthouse (observability)       │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 5 — Evolution:    Phoenix (self-improvement) · Crucible (eval)     │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 4 — Validation:   Oracle (deterministic verifiers)                 │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 3 — Knowledge:    Codex (skills) · Mnemos (memory)                 │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 2 — Cognition:    Hydra (models, planner, racing)                  │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 1 — Control:      Forge (coordinator, workers, loop)               │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 0 — Substrate:    Arsenal (MicroVMs, tools, MCP gateway)           │
└──────────────────────────────────────────────────────────────────────────┘
```

Each layer is replaceable. A user who wants their own sandbox can swap Layer 0. A user who wants a different validator can swap Layer 4. The contracts between layers are the stable surface.

---

## 3. The 10 pillars in depth

### Pillar 1 — **Hydra**: Cognitive Core

> Multi-model orchestration with a planner/summarizer split and parallel model racing on hard subproblems.

**Job.** Turn a problem statement into a sequence of tool calls and natural-language plans, with strong resilience to single-model failure modes (hallucination, tunnel-vision, refusal).

**Design.**
- **Planner / Summarizer split** (from HackSynth). Planner emits one bounded action; Summarizer compresses the cumulative trace and feeds the next planner step. This is the most empirically validated pattern for offensive-sec agents — it directly addresses context bloat and command repetition.
- **Model racing** on contested subtasks (from `verialabs/ctf-agent`, BSidesSF 2026 winner: 52/52 challenges). Run N models on the same flag/subgoal; first verifiable solution wins. Costly, but the variance reduction is large.
- **Model tiering.** Frontier model for planning & novel reasoning. Cheap model for summarization, regex/grep classification, and tool-call repair. (CAI runs 300+ models; we adopt the same provider-agnostic stance via LiteLLM-style gateway.)
- **ReACT loop** as default, but with a verifier short-circuit (Oracle, Pillar 6) — if a finding is verified, the loop exits; no "let me also try…" sprawl.
- **Refusal handling.** Frontier models refuse some offensive actions. Scarlight detects refusals, classifies them (policy refusal vs. capability gap), and either re-prompts with engagement context or routes to a different model.

**Tradeoffs.**
- Racing burns tokens. Default is single-model; racing activates when a subtask exceeds budget.
- Tiered models add latency. We bound it: small model gets ≤1 retry before escalation.

**Prior art:** HackSynth, ctf-agent, CAI, PentestGPT v2.

---

### Pillar 2 — **Forge**: Control Plane

> Coordinator + ephemeral workers, stateless-reducer loop, pause/resume on persistent state.

**Job.** Orchestrate the lifecycle of an offensive engagement: many parallel workers, each short-lived and narrow; a single coordinator that maintains the global plan; durable state so engagements survive context-window exhaustion, process restarts, and operator handoffs.

**Design.**
- **Coordinator-worker topology** (from XBOW). The coordinator holds the long-horizon plan and the target attack-surface model. Workers receive a single mission ("test login endpoint for SQL injection on `https://target/login`"), a fresh context, and a hard time/token budget. Workers retire on completion. This is the only known architecture that scales offensive AI to large targets without context collapse.
- **Stateless reducer agent** (from 12-Factor Agents). Workers are pure functions of `(engagement_state, mission) → (next_actions, new_state_delta)`. State lives in the FS + git + DB, not in the loop. Workers can be serialized, forked, replayed.
- **Pause/resume** as a first-class primitive. An engagement can pause for human approval (Aegis), for an external trigger (target available), or for cost ceiling. Resume is a single API call.
- **Ralph-style loops** for long horizons: when context fills, the worker writes a progress note, the coordinator spawns a successor with a fresh context, the successor reads the progress note and continues.
- **Triggers from anywhere.** Engagements are launched by CLI, GitHub Action, Slack command, webhook, or cron. Scarlight does not own the UX; it exposes a clean control API.

**Tradeoffs.**
- Stateless workers mean every mission incurs setup cost. We amortize with warm-pool MicroVMs (Arsenal) and a shared target-graph (Mnemos).
- Coordinator becomes a single point of orchestration failure. Mitigated with checkpointing every N decisions; coordinator state is replayable from the journal.

**Prior art:** XBOW, 12-Factor Agents, Anthropic's "Scaling Managed Agents", DeerFlow, Symphony.

---

### Pillar 3 — **Arsenal**: Execution Substrate

> MicroVM-isolated sandboxes pre-loaded with the offensive toolchain, exposed to the agent through MCP and a credential-injecting gateway.

**Job.** Give the agent real tools (nmap, sqlmap, Burp, pwntools, radare2, ghidra, metasploit, ffuf, nuclei, hashcat, john, mimikatz, …) without giving it the keys to the host or the internet.

**Design.**
- **MicroVM-per-worker** (Firecracker / Arrakis / Tensorlake). Each worker runs in its own micro-VM with snapshot/restore, so a worker that gets compromised by the target (rare but possible — *we're attacking real things*) cannot escape into the coordinator or the operator's machine.
- **Curated tool image**. A single signed OCI image is the "kit". Versions are pinned. Reproducibility is a hard requirement — every engagement record references the exact image hash.
- **MCP-native tool interface** (Model Context Protocol). Every tool — `nmap`, `sqlmap`, `burp`, `radare2`, `pwntools` — is wrapped as an MCP server. This means: tools are interoperable with other harnesses, the same tool surface works for Claude/GPT/Gemini, and third parties can ship their own MCP-wrapped tools.
- **Egress gateway with allowlist** (from IronClaw). The MicroVM has *no* default internet. All outbound traffic passes through a gateway that enforces the engagement's signed scope file (Aegis). Out-of-scope packets are dropped and logged.
- **Credential injection at the gateway**, never in the prompt or the worker process. The agent says "use credential `target_admin`"; the gateway substitutes the secret on the wire.
- **WASM tier for untrusted tools** (from IronClaw). Skills generated by the agent itself (Codex) run first in a WASM sandbox with capability tokens, before being promoted to MicroVM execution.
- **Warm pools.** N pre-snapshotted MicroVMs ready to accept missions. Spin-up is hundreds of milliseconds, not seconds.
- **Browser execution** is a Chromium-via-CDP MCP server (cf. browser-use, Browser Harness, Steel) — phishing simulation, web exploitation, OAuth flow attacks, and recon use the same browser substrate.

**Tradeoffs.**
- MicroVMs cost more than containers. The security win is worth it; the throughput cost is absorbed by warm pools.
- MCP wrapping every tool is engineering work. Mitigated by a default `Tool` interface that wraps any CLI in a single Python class.

**Prior art:** Arrakis, Tensorlake, Firecracker, IronClaw, Daytona, ctf-agent toolchain, CAI tool ecosystem.

---

### Pillar 4 — **Codex**: Skill Library

> Voyager-style executable skills, autonomously created after engagements, indexed and composable, versioned in git.

**Job.** Turn every engagement into a durable, reusable artifact. The first time Scarlight cracks an IDOR pattern, it writes a skill. The second time, it reuses. The thousandth time, it composes a more sophisticated chain. This is the substrate for self-improvement (Phoenix, Pillar 7).

**Design.**
- **Skills are executable code** (from Voyager). A skill is a Python module exposing `run(target, context) → finding`, with structured metadata (MITRE ATT&CK ID, CVE references, prerequisites, side-effect profile, runtime estimate).
- **Skills are autonomously created** (from Hermes Agent). At the end of every successful engagement step, a Skill Synthesizer agent (a specialized Hydra mode) asks: "did we just do something worth writing down?" If yes, it extracts the procedure, parameterizes it, writes tests, and submits it to the library.
- **Compositional**. Skills can call skills. A `web_recon` skill calls `subdomain_enum`, `dir_brute`, `tech_fingerprint`, `cred_test`, each of which is independently versioned. Voyager proved this works.
- **Indexed by embedding + structured tags**. Retrieval at engagement time uses both: vector search on "what does this skill do" and structured filter on "is this skill in scope for my engagement type / target tech stack / authorization level".
- **Self-improvement during use** (from Hermes / Voyager iterative prompting). Skills emit telemetry; Phoenix's curriculum identifies underperforming skills; the Skill Refiner agent rewrites them.
- **Git-versioned**. Every skill is a commit. Bad skills can be reverted. A canary/promote workflow ensures freshly synthesized skills run in shadow mode before becoming default.
- **Skill marketplace / community library** (analogous to agentskills.io, Awesome lists). Scarlight ships with a core library; community contributions extend it. Cryptographic signing for trusted skill packs.
- **Tagged by MITRE ATT&CK + CWE + OWASP**. Skills are queryable as `mitre:T1190` (initial access via public-facing app) or `cwe:CWE-89` (SQL injection). This is how the agent picks the right tool at the right moment.

**Tradeoffs.**
- Skill bloat: too many skills makes retrieval noisy. Mitigated by usage decay — skills not used in 90 days are demoted from default retrieval (still accessible by explicit query).
- Skill-on-skill recursion can loop. Hard depth limit (default 5).
- Autonomously created skills can be wrong. They pass through the canary pipeline + Oracle verification before promotion.

**Prior art:** Voyager (the canonical pattern), Hermes Agent, agentskills.io, Anthropic Skills system, SuperClaude framework.

---

### Pillar 5 — **Mnemos**: Memory & Context Engineering

> Three-tier memory: episodic per-engagement, semantic across engagements, and a target knowledge graph that compounds across the entire operator.

**Job.** Solve the #1 reliability problem identified by RiskInsight 2026: agents "miss obvious findings" (e.g., admin panel + default creds) because context collapses. Memory is the only durable defense.

**Design.**
- **Episodic memory.** Per-engagement timeline of every action, observation, decision, and finding. Stored as JSONL + SQLite FTS5 (Hermes pattern). Replayable for forensics (Lighthouse).
- **Semantic memory.** Cross-engagement: "techniques that worked against tech X", "patterns of fragile auth in framework Y", "CTF tropes that fooled us last time". Embedded + retrievable by Hydra during planning.
- **Target knowledge graph.** A first-class graph per target: subdomains → services → endpoints → params → credentials → findings. Populated by every recon worker; queried by every exploitation worker. This is the single most important data structure in Scarlight — it is what makes the 1000th worker on a target smarter than the 1st.
- **AGENTS.md-style standing context** per engagement. A signed `engagement.yaml` (scope, ROE, target tech stack, prior findings, operator notes) is injected into every worker's context.
- **Tool output offloading** (from Anthropic / Claude Code harness guidance). Large outputs (nmap scan, Burp crawl) go to the filesystem; only the summary + a file pointer enter the context. Workers `read` the file when they need detail.
- **Compaction** when context approaches 80% of window: summarizer compresses with a domain-aware prompt ("preserve all hostnames, credentials, finding IDs, and CVEs verbatim").
- **Honcho-style operator modeling** (from Hermes). Scarlight builds a model of the operator's preferences: how aggressive, how exhaustive, what's in/out of scope by default, what reporting format they want.

**Tradeoffs.**
- Cross-engagement semantic memory needs careful tenancy. Default: per-operator. Multi-tenant memory is opt-in with explicit cross-tenant skill sharing.
- Target graph quality depends on recon worker quality. Phoenix's curriculum prioritizes recon skill improvement because of this dependency.

**Prior art:** Hermes Agent (FTS5, Honcho), Anthropic context-engineering posts, Mem0, claude-mem, Trellis, AGENTS.md.

---

### Pillar 6 — **Oracle**: Deterministic Validation

> AI discovers; deterministic logic validates. Every finding is accompanied by a reproducible, non-destructive proof-of-exploit.

**Job.** Kill the #1 failure mode of offensive AI: hallucinated findings. RiskInsight 2026 documented this as the dominant failure even at frontier models. XBOW reached #1 on HackerOne by separating discovery from validation. Scarlight builds this in from day one.

**Design.**
- **Every skill exports a `verify()` method.** When a skill says "I found SQLi at param `id` on `/login`", `verify()` re-runs a minimal, deterministic check (e.g., time-based blind: `id=1' AND SLEEP(5)--` returns >4s; `id=1' AND SLEEP(0)--` returns <1s; assertion holds).
- **Proof-of-exploit artifacts.** A finding is incomplete without (a) the request that triggered it, (b) the response that confirmed it, (c) the deterministic check that re-verifies, (d) a non-destructive exploit demonstration.
- **Non-destructive challenge generation** (from XBOW). For dangerous classes (RCE, deserialization, SSRF), Scarlight emits a *demonstration* payload (`whoami`, `id`, DNS callback to scarlight controlled domain) — never destructive ones. The skill metadata declares what classes of payload are acceptable.
- **Subtask validators** (from Cybench). Long missions break into subtasks with their own verifiers. Stuck on a subtask → escalate (Hydra: model racing, or Aegis: human approval).
- **Reproducibility check.** Every finding must reproduce in N runs (default 3). Flapping findings are flagged for human review, not reported as vulnerabilities.
- **Verifier-based reward signal.** Phoenix's self-improvement loop uses Oracle verdicts as the empirical signal (cf. PrimeIntellect's `verifiers`, NeMo Gym, RL with verifiable rewards).

**Tradeoffs.**
- Writing verifiers is engineering work. Mitigated by: verifier templates per vulnerability class, autonomous verifier synthesis from successful exploits, and a "skill without verifier" status that prevents the skill from being trusted.
- Some findings are inherently probabilistic (e.g., timing attacks, race conditions). Verifiers report statistical confidence, not boolean.

**Prior art:** XBOW (the canonical pattern), Cybench subtask evaluators, `verifiers`, NeMo Gym, OpenAI Evals.

---

### Pillar 7 — **Phoenix**: Self-Improvement Engine

> The agent rewrites its own harness, generates its own skills, and validates each modification on Crucible. This is the "superintelligence" pillar.

**Job.** Beat the frontier-model ceiling that currently bounds all offensive AI. The thesis: a harness that can rewrite itself, with Cybench/CAIBench/HackSynth as the reward signal, will exceed any static harness on a fixed model. Darwin Gödel Machine demonstrated this on SWE-bench (+30pp). Scarlight applies the same to offensive security.

**Design (three nested loops).**

1. **Skill-level loop (fastest)**: every engagement produces skill candidates; Codex's Canary pipeline evaluates them on Crucible's regression set; passing skills promote.
2. **Strategy-level loop (medium)**: the curriculum agent identifies areas where Scarlight underperforms (e.g., "weak on reverse engineering tasks"), spawns synthetic CTF-style training engagements, and lets Hydra solve them to generate skills. Cybench's PicoCTF tier is the natural curriculum source.
3. **Harness-level loop (slowest)**: a DGM-style agent reads the harness's own source (Forge, Hydra, Mnemos), reads Lighthouse traces of failures, proposes code changes to the harness itself, runs the modified harness on Crucible, and keeps the mutation if it improves the score. Modifications archived in a population (DGM's archive pattern) so stepping-stones aren't lost.

**Critical design choices.**
- **Archive, not hill-climbing** (DGM). Keep every variant; later mutations can fork from earlier "abandoned" branches.
- **Staged evaluation** (DGM: 10 → 50 → 200 tasks). Cheap screen, then expensive validation. Stops the budget bleed.
- **Empirical, not formal, validation.** We're not proving anything theoretical; we trust Crucible's regression suite.
- **Sandboxed self-modification.** The DGM mutator runs in its own MicroVM, with no access to the production skill library or memory store. Promotion to production requires a passing canary + a human approval (Aegis).
- **Safety net.** A modification that *reduces* Crucible scores below the previous-best by more than ε is rejected. A modification that introduces new CWEs or new egress destinations is rejected automatically.

**Tradeoffs.**
- Cost. DGM's SWE-bench runs take 2 weeks. We mitigate by aggressive staging and by limiting harness-level mutations to one per week, with skill-level loops running continuously.
- Alignment risk: an agent that rewrites its own harness could degrade safety properties. Mitigated by: Aegis is immutable from the agent's perspective (it lives in a separate trust domain); harness modifications cannot touch the gateway, the credential vault, the scope enforcer, or the audit log.

**Prior art:** Darwin Gödel Machine (the canonical pattern), Voyager (skill-loop), Hermes Agent (skill creation), auto-harness, NeMo Gym.

---

### Pillar 8 — **Crucible**: Evaluation Harness

> Cybench- and CAIBench-compatible eval suite, regression-guarded, A/B-comparable across harness versions.

**Job.** Provide the empirical signal that Phoenix optimizes against, and the regression guarantee that prevents self-modification from breaking the harness. Also: provide an honest, public scoreboard so the community can see whether Scarlight is improving.

**Design.**
- **Native Cybench support.** All 40 Cybench tasks runnable as a single command: `scarlight eval cybench`. Subtask-guided and unguided modes. Results comparable to published baselines.
- **Native CAIBench support.** All five CAIBench categories (Jeopardy CTF, attack-defense, cyber range, knowledge QA, privacy/PII).
- **Native HackSynth PicoCTF + OverTheWire** for cheap, fast smoke tests.
- **Internal regression suite.** Scarlight maintains its own private suite of seeded, deterministic challenges that exercise each skill in Codex. Skills cannot be promoted without passing.
- **Engagement-replay benchmarks.** Real (sanitized, scope-respecting) past engagements become regression cases.
- **Cost / token / latency metrics** alongside success — a skill that solves 5% more tasks at 10× the cost is not necessarily a win. Phoenix optimizes Pareto.
- **A/B harness comparison.** Run mutation X against mutation Y on the same task set; verdict is statistically significant or no-op.
- **Public leaderboard.** Scarlight publishes its own scores publicly. No private "internal" results. Trust comes from auditability.

**Tradeoffs.**
- Eval cost is real. Cybench full run is expensive. Mitigated by tiered evaluation (smoke → standard → full).
- Benchmark gaming. The harness can overfit to Crucible. Mitigated by: held-out tasks rotated quarterly, real-engagement replay as out-of-distribution signal.

**Prior art:** Cybench, CAIBench, HackSynth, SWE-bench, auto-harness, Inspect Evals, AgentBench.

---

### Pillar 9 — **Aegis**: Safety, Authorization, Scope

> Non-negotiable. The harness refuses to act outside a signed engagement contract. Credentials never enter the model context. Out-of-scope egress is dropped and logged.

**Job.** Make Scarlight legally usable, ethically defensible, and resistant to misuse — without compromising the offensive capability that legitimate operators need. Offensive tools without scope enforcement are liability factories. Offensive tools with rigorous scope enforcement are the standard professional product.

**Design.**
- **Signed engagement contract.** Every engagement begins with a YAML scope file: in-scope domains/IPs/asset classes, ROE, allowed payload classes, time windows, authorization references (statement of work, bug-bounty program URL, CTF event ID). The operator signs it (Ed25519). The signature is stored with every trace and every report.
- **Enforcement at the gateway, not in the model.** Aegis is *outside* the agent's trust boundary. No prompt-injection of the form "ignore previous scope" can succeed because the agent literally cannot speak past the gateway. The gateway validates every packet against the signed scope and drops violations.
- **Capability tokens per worker.** Workers receive a JWT scoped to (engagement, mission, time-bound, action-classes). Token-less actions fail.
- **Credential vault.** Secrets are stored in a vault (sops/age/Hashicorp-style). The agent receives credential *handles*, never values. The gateway substitutes on-wire.
- **Payload class allowlist.** Engagement contract specifies which payload classes are allowed (e.g., "non-destructive RCE demos only, no persistence, no lateral movement"). Skills declare their payload class; mismatches block.
- **Authorization modes.** Four canonical modes, each with different default policies:
  - `lab` — local-only network, anything goes (CTF, training).
  - `ctf` — connected to specified CTF platform, scoped to that platform.
  - `bug_bounty` — connected to specific program, ROE scraped from program page + operator-signed.
  - `pentest` — formal SoW reference, full audit, mandatory operator approvals on high-blast actions.
  - `red_team` — extended scope, persistence allowed, stealth profile active.
- **Human-in-the-Loop gates.** High-blast actions (anything outside `lab`/`ctf` mode that touches production data, anything that could affect availability, anything that touches a new IP not on the allowlist) require operator approval. Approval queue is a structured tool call (12-Factor pattern).
- **Drift detection.** If the agent is repeatedly attempting out-of-scope actions, Aegis suspends the engagement and notifies the operator.
- **Tamper-evident audit.** Every Aegis decision is logged to Lighthouse with cryptographic chaining; modifications detectable.
- **Self-improvement firewall.** Phoenix cannot modify Aegis. Aegis lives in a separate process with a separate codebase that the harness-level mutator has no access to. Modifications to Aegis require human review and PR merge.

**Tradeoffs.**
- Friction. Real operators don't want approval prompts every 10 seconds. Mitigated by: smart batching, mode-aware thresholds, operator-tuned approval policies.
- Determined misuse is hard to prevent. Mitigated by: making misuse obvious in logs, leaning on legal not technical defense ([`CODE_OF_USE.md`](../CODE_OF_USE.md)).

**Prior art:** IronClaw (capability-based permissions + gateway), CAI (guardrails), Claude Code auto-mode (classifier-backed approval delegation), Anthropic's "Sandboxing for safe autonomy".

---

### Pillar 10 — **Lighthouse**: Observability & Forensics

> Every action signed, traced, replayable, and exportable. Trust in offensive AI requires complete chain of custody.

**Job.** Make every Scarlight engagement fully auditable. The professional offensive industry needs this for: (a) client reporting, (b) post-engagement forensics, (c) regulatory compliance (GDPR Art. 30 records, NIS2 incident records), (d) Scarlight's own debugging, (e) Phoenix's self-improvement signal.

**Design.**
- **OpenTelemetry-native.** Every action — model call, tool invocation, gateway decision, validation verdict, memory read/write — emits an OTel span. Compatible with Langfuse, Arize Phoenix, Grafana Tempo.
- **Append-only signed journal.** Per-engagement JSONL log with hash chain (each entry references the hash of the previous). Tamper-evident. Exportable.
- **Replayable sessions.** A session can be replayed from the journal: same prompts, same tool outputs (cached), shows what the agent saw. Used for: bug forensics, client demos, training data for Phoenix.
- **Cost / time / token metrics.** Per-engagement, per-skill, per-model, per-worker. Pareto-comparable across harness versions.
- **Findings export.** Markdown report, SARIF, DefectDojo JSON, custom client templates. Operator-controlled.
- **Trace visualization.** Embedded web UI (or Langfuse integration) for inspecting an engagement: timeline, decision tree, model races, validation verdicts, scope violations.
- **Privacy.** Engagements may contain client-sensitive data. Lighthouse supports local-only mode (no telemetry off-host), self-hosted Langfuse, and explicit field-level scrubbing rules before export.

**Tradeoffs.**
- Volume. Full tracing on a long engagement is gigabytes. Mitigated by tiered retention.
- Privacy vs. shareability. Default to private; the public scoreboard (Crucible) exports only aggregate metrics.

**Prior art:** Langfuse, Arize Phoenix, OpenLLMetry, OpenTelemetry, claude-code-reverse, Tracecat, CAI's tracing.

---

## 4. The cross-cutting concerns

Beyond the ten pillars, Scarlight standardizes on:

- **Protocols.** MCP for tools. AGENT.md / AGENTS.md for repo-local agent instructions. ACPX-style headless control for cross-harness scripting. SARIF / DefectDojo for findings export. Ed25519 signatures for engagement contracts.
- **Languages.** Python for the harness control plane (ecosystem advantage in offensive sec — pwntools, scapy, impacket, mitmproxy). Rust for the gateway, scope enforcer, and credential vault (memory safety, performance, no GC pauses on the security-critical path). TypeScript for the web UI. WASM for skill sandboxes.
- **Distribution.** Single binary CLI (`scarlight`) embedding a Python runtime; Docker image for the coordinator + worker pool; Helm chart for cluster deployments. Homebrew + apt + Windows installer for the CLI.
- **Licensing.** Apache 2.0 for the harness. Authorized Use Policy ([CODE_OF_USE.md](../CODE_OF_USE.md)) as a separate document, enforced by community norms and contributor agreement. Some high-risk capabilities (e.g., autonomous lateral movement) are *not* included in the default skill library; community packs distribute them separately.

---

## 5. What's deliberately out of scope (v0)

- **Defensive (blue-team) workflows.** Scarlight is offensive-first. Defensive integrations may come in v2.
- **Closed-source frontier-model dependency.** Scarlight runs on local + frontier models alike. We will not adopt features that require a single commercial provider.
- **Agentic C2 / persistence frameworks.** These exist (Sliver, Mythic, Cobalt Strike). Scarlight integrates *with* them via MCP rather than rebuilding.
- **Exploit weaponization for unreported CVEs.** Skills must reference disclosed CVEs or operator-supplied research; novel 0day weaponization is not a feature of the default library.

---

## 6. The single most important decision

If we had to defend one design choice, it would be the **Phoenix–Oracle coupling**: self-improvement must be gated on deterministic verification, not on model-as-judge.

Every other choice in this document follows from the same principle: **structure the harness so that LLM hallucination cannot become a durable artifact.** Memory is structured. Skills are verified before promotion. Findings require proof-of-exploit. Self-modification is regression-tested. Scope is gateway-enforced. Audit logs are tamper-evident.

LLMs are unreliable at the action level. Scarlight wraps them in a system that is reliable at the engagement level. That is the only way to get to "cyber superintelligence" without producing the next ClawJacked-style headline.

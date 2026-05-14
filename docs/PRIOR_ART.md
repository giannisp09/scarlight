# Prior Art

> Scarlight stands on a tall stack of OSS work. This document records what we read, what we inherit, and where we diverge. It is also a reading list for new contributors.

---

## 1. The agent-harness ecosystem (general)

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Picrew/awesome-agent-harness** (174 resources, 9 categories) | Taxonomy: harness vs. framework vs. runtime; cross-cutting themes (long-horizon state, sandbox isolation, MCP, worktrees, decoupling brains from hands) | — |
| **Claude Code** (Anthropic) | Hooks model, AGENTS.md, skills, sandbox patterns, approval delegation, harness engineering philosophy | Closed-source, coding-focused |
| **OpenCode** (anomalyco) | Role/subagent structure, runtime patterns | Generic, no offensive-sec focus |
| **OpenHands** | Long-horizon repo-level workflows | Coding-domain only |
| **SWE-agent / mini-swe-agent** | Minimal harness composition; explicit tool loops | Coding-domain only |
| **OpenClaw** | Reference for the "Hermes/OpenClaw of offensive sec" positioning; lessons from CVE-2026-25253 (broad exposure surface, default-deny matters) | Broad surface, host-level execution |
| **Hermes Agent** (Nous Research) | Self-improvement loop, autonomous skill creation, FTS5 session search, Honcho user modeling, agentskills.io interop | General-purpose; not offensive-sec |
| **NanoClaw** (qwibitai) | Container isolation patterns, channel routing | Coding/general |
| **IronClaw** (NEAR) | WASM sandbox for untrusted tools, capability tokens, gateway-side credential injection, egress allowlisting | General; we extend pattern with MicroVMs |
| **CLI-Anything** (HKUDS) | Unified CLI as agent control surface | General |
| **DeerFlow** (ByteDance) | Long-horizon super-agent integration patterns | General |
| **AutoGen / LangGraph / LangChain** | Internal framework deps (optional, swappable) | We are not a framework |
| **Symphony** (OpenAI) | Ticket-driven orchestration; engagement = ticket-like artifact | — |
| **Archon** (coleam00) | YAML-defined workflow phases, isolated worktrees, validation gates | Coding |
| **Anthropic engineering posts** ("Building effective AI agents", "Effective harnesses for long-running agents", "Effective context engineering", "Scaling Managed Agents", "Sandboxing for safe autonomy", "Demystifying Evals", "Code execution with MCP") | Foundational principles for every pillar | — |
| **12-Factor Agents** (HumanLayer) | Own prompts, own context, tools = structured outputs, stateless reducer, pause/resume, compact errors, small focused agents, trigger anywhere | — |
| **The Anatomy of an Agent Harness** (LangChain) | Decomposition: state, exec, control flow, planning, context, knowledge; harness vs framework vs runtime | — |
| **Harness Engineering** (Martin Fowler) | Architectural perspective on entropy control | — |

---

## 2. Offensive-security AI prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **CAI / Cybersecurity AI** (Alias Robotics) | Closest prior art. Inherit: 8-pillar mental model (agents/tools/handoffs/patterns/turns/tracing/guardrails/HITL), ReACT agents, MCP integration, OpenTelemetry tracing, 300+ model support, agentic patterns (swarm/hierarchical/CoT/recursive), guardrails layer | Host-level execution (no sandbox), no self-improvement, no skill library |
| **HackSynth** | Planner/Summarizer split (this is the empirical winner for offensive-sec ReACT), bounded observation windows, command-tagging via `<CMD></CMD>`, 20-step budget pattern, PicoCTF/OverTheWire as eval | Two-module simplicity is the floor; we extend it |
| **PentestGPT v2 / Excalibur** | Modular reasoning/generation/parsing architecture, 91% on XBOW web set | Semi-autonomous; we aim further along the autonomy axis |
| **HackingBuddyGPT** | Privesc-focused agent; "50 lines of code or less" minimalism as a reference floor | Privesc-only scope |
| **ctf-agent** (verialabs, BSidesSF 2026 winner, 52/52) | Parallel model racing pattern, message-bus for cross-solver insights, Docker tool-image (radare2, pwntools, ROPgadget, angr, SageMath, z3, volatility3, Sleuthkit, steghide), CTFd poller integration, "never gives up" retry logic | CTF-only |
| **XBOW** (closed-source) | Coordinator + thousands of ephemeral workers, deterministic validators, non-destructive proof-of-exploit, retire-on-completion to prevent context collapse, "AI discovers, logic validates" | Closed source; we replicate the architecture as OSS |
| **Cybench** | The benchmark substrate. 40 tasks across 6 categories (crypto, web, rev, forensics, misc, pwn), subtask-guided vs unguided modes, scoring metrics. Native target for Crucible | — |
| **CAIBench** | Meta-benchmark structure: Jeopardy CTF + Attack-Defense + Cyber Range + Knowledge + Privacy. Difficulty tiers. We integrate all five | — |
| **RapidPen / AutoPentester / CyberStrikeAI / HexStrike / WhiteRabbitNeo** (Hadrian's 70-tool survey) | Confirmation of recon being the strongest current capability, defense-evasion / persistence / C2 / exfil being the weakest — guides Phoenix's curriculum | Most are model wrappers; none have self-improvement |

---

## 3. Self-improvement prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Voyager** (MineDojo) | The canonical pattern: automatic curriculum + skill library as executable code + iterative prompting with self-verification. Compositional skills. Top-5 retrieval. This is the substrate for Codex (Pillar 4) | Minecraft-domain; we re-instantiate for offensive sec |
| **Darwin Gödel Machine** (Sakana AI) | The canonical harness self-modification pattern. Archive of variants (not hill-climbing). Staged eval (10 → 50 → 200). Empirical validation in place of formal proofs. Sandboxed mutation. Parent selection by performance + underexploration. +30pp on SWE-bench is the existence proof | We never let DGM touch Aegis; modifications are gated by Crucible + human approval |
| **Hermes Agent** (Nous Research) | Autonomous skill creation after complex tasks, FTS5 cross-session search, Honcho dialectic user modeling, agentskills.io open standard. "Builds a deepening model of who you are across sessions" — we apply this to operator modeling | General-purpose skill set |
| **STARC / Gödel Machine (Schmidhuber)** | The theoretical lineage. Self-rewriting code under proof-of-improvement | Formal proofs unsuitable for real systems; we trust empirical validation per DGM |
| **Voyager-in-LangGraph / CrewAI** | Production patterns for skill libraries | — |

---

## 4. Substrate / sandbox prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Arrakis** (abshkbh) | Self-hosted MicroVM with snapshot/restore via REST/SDK/MCP | — |
| **Tensorlake** | Serverless MicroVM sandbox; snapshots; suspend/resume | — |
| **Firecracker** (AWS) | The underlying MicroVM tech | — |
| **E2B / Daytona / CUA** | Cloud sandbox APIs | We support but do not require a cloud provider |
| **agent-infra/sandbox** (alibaba) | All-in-one substrate (browser, shell, files, MCP, IDE server) — reference for our default tool image | — |
| **OSS-Fuzz Gen** (Google) | LLM-powered fuzzing in controlled execution; influences how we frame fuzzing skills | — |
| **kubernetes-sigs/agent-sandbox** | Stateful, stable-identity sandbox primitives for K8s deployments | — |
| **SWE-ReX** | Sandboxed execution patterns for coding agents | — |
| **Capsule** | WebAssembly sandboxes for durable runtime | We use WASM for skill-tier execution, MicroVMs for full workers |

---

## 5. Evaluation prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Cybench** | First-class target. 40-task suite is our regression floor | — |
| **CAIBench** | First-class target. Adds attack-defense + cyber range + privacy | — |
| **HackSynth's PicoCTF/OverTheWire suite** | Cheap smoke tests | — |
| **SWE-bench / SWE-bench Pro** | Methodology only — we are not a coding harness | Domain mismatch |
| **AgentBench / Terminal-Bench / Inspect Evals / Harbor / NeMo Gym** | Methodology + RL environment shape | — |
| **verifiers** (PrimeIntellect) | Verifier-based eval / RL pattern | — |
| **Promptfoo / DeepEval / RAGAS / EvalScope** | Reference for unit-level prompt/skill evaluation | — |
| **auto-harness** (neosigmaai) | Benchmark-gated optimization, failure mining, regression guards — directly applicable to Phoenix → Crucible coupling | — |

---

## 6. Memory / context prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Hermes Agent** | FTS5 + LLM summarization for cross-session recall; Honcho user modeling | — |
| **Mem0 / Letta / claude-mem** | Memory architecture patterns | — |
| **CCPM / Trellis / planning-with-files** | Persistent, file-based planning | — |
| **AGENTS.md / AGENT.md** | Standing-instructions format | — |
| **Context-Engineering Handbook** (davidkimai) | First-principles guidance | — |

---

## 7. Observability / governance prior art

| Source | What we take | What we leave |
|--------|--------------|---------------|
| **Langfuse** | OSS tracing platform — first-class Lighthouse integration | — |
| **Arize Phoenix** | Alternative OSS tracing | — |
| **OpenLLMetry** | OpenTelemetry instrumentation | — |
| **MLflow / Helicone / AgentOps / Laminar / Opik / TensorZero** | Reference observability architectures | — |
| **LiteLLM** | Provider-agnostic LLM gateway — Hydra inherits this pattern | — |
| **CAI's Phoenix-based tracing** | Validation that OTel-based tracing works for security agents | — |
| **Tracecat** | Security automation workflow patterns | — |
| **AgentGateway / Plano / Archestra / ContextForge / Haft** | Gateway/proxy/governance patterns for agentic systems | — |

---

## 8. The key papers (academic)

- *Cybench: A Framework for Evaluating Cybersecurity Capabilities and Risks of Language Models* — performance 17.5% → 93% over 18 months
- *HackSynth: LLM Agent and Evaluation Framework for Autonomous Penetration Testing*
- *CTFAgent: An LLM-powered Agent for CTF Challenge Solving* — 88% outperform on PicoCTF
- *LLMs as Hackers: Autonomous Linux Privilege Escalation Attacks*
- *What Makes a Good LLM Agent for Real-world Penetration Testing?*
- *A Survey of Agentic AI and Cybersecurity: Challenges, Opportunities and Use-case Prototypes*
- *Cybersecurity AI (CAI): An open framework for AI Security* — Vilches et al. 2026
- *Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents*
- *Voyager: An Open-Ended Embodied Agent with Large Language Models*

---

## 9. The closed/commercial reference points

- **XBOW** — coordinator-worker + validators; reached #1 HackerOne. Sets the bar for autonomous offensive AI performance.
- **Hadrian, MindFort, Penligent** — commercial AI pentesting platforms; we are the OSS counterweight.
- **Pentera, Horizon3 NodeZero** — autonomous breach-and-attack-simulation platforms (older generation).

---

## 10. Where Scarlight is novel

Combining the following in one OSS harness is, to our reading, unprecedented:

1. **Self-improvement on offensive-security benchmarks.** DGM exists for coding; Voyager exists for Minecraft; Hermes exists for general-purpose. None apply self-modification to offensive sec with Cybench/CAIBench as the reward signal.
2. **MicroVM-isolated coordinator-worker topology for offensive AI, as OSS.** XBOW has the topology but is closed. CAI has the agents but no isolation.
3. **Skill library tagged by MITRE ATT&CK + CWE + OWASP, with autonomous skill synthesis.** No offensive-sec tool we found ships this.
4. **Deterministic Oracle as a first-class pillar.** XBOW pioneered the discover/validate split; we are the first OSS harness to make it a non-negotiable architectural primitive.
5. **Aegis as a separate trust domain that Phoenix cannot mutate.** A self-improving agent that *cannot* erode its own safety properties is a category we haven't seen documented.

The bet: each of these alone is incremental. Together they compound. That is what we mean by "cyber superintelligence" — not a smarter model, but a harness whose capability surface grows monotonically with use.

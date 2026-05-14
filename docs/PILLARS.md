# Pillars at a glance

One-pager reference. Full discussion in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`pillars/anvil.md`](./pillars/anvil.md).

| # | Pillar | Layer | Job (one line) | Primary prior art |
|---|--------|-------|----------------|-------------------|
| 1 | **Hydra** | Cognition | Multi-model planner/summarizer with model racing on hard subtasks; local-first tiering | HackSynth, ctf-agent, CAI, TrustedSec benchmarks |
| 2 | **Forge** | Control | Persistent coordinator + dynamic workers + bounded sub-workers (depth ≤ 3); five topology profiles chosen adaptively; shared target-graph + engagement bus; code-mode subloop | XBOW, Anthropic multi-agent research, Claude Code Task tool, AdaptOrch, HPTSA, deepagents |
| 3 | **Arsenal** | Substrate | MicroVM-isolated workers, MCP-native tools, egress gateway | Arrakis, IronClaw, ctf-agent toolchain |
| 4 | **Codex** | Knowledge | Voyager skill library, autonomous skill creation, MITRE/CWE/OWASP-tagged | Voyager, Hermes, agentskills.io |
| 5 | **Mnemos** | Knowledge | Episodic + semantic + target-graph memory, cross-session FTS5 | Hermes, Mem0, AGENTS.md |
| 6 | **Oracle** | Validation | Deterministic verifiers, proof-of-exploit, non-destructive challenges | XBOW, Cybench, verifiers, security-verifiers |
| 7 | **Phoenix** | Evolution | Tiered code self-modification (T0–T3), archive, anti-reward-hacking | Darwin Gödel Machine, Voyager, OpenAI CoT-monitoring |
| 8 | **Crucible** | Evolution | Cybench/CAIBench/HackSynth eval suites, regression guards, verifiers-as-environments | Cybench, CAIBench, SWE-bench, PrimeIntellect verifiers |
| 9 | **Aegis** | Trust & Ops | Signed contract, gateway scope, credential vault, HITL, four deployment modes incl. air-gapped | IronClaw, CAI guardrails, Claude Code auto-mode |
| 10 | **Lighthouse** | Trust & Ops | OTel tracing, signed audit journal, replayable sessions, SARIF export, Anvil-trajectory export | Langfuse, OpenLLMetry, CAI tracing |
| 11 | **Anvil** | Evolution | Opt-in RLVR via `prime-rl` + `verifiers` + Crucible; SFT/DPO/GRPO/DAPO; federated training | PrimeIntellect verifiers + prime-rl, INTELLECT-3, intertwine/security-verifiers |

## The 11 in one sentence each

1. **Hydra** decides what to do next, choosing between local and frontier models.
2. **Forge** runs the agent loop reliably across long engagements, including a code-mode subloop.
3. **Arsenal** provides isolated environments and real tools (offensive + coding).
4. **Codex** stores what worked and reuses it next time.
5. **Mnemos** remembers everything about the target.
6. **Oracle** proves a finding is real before we believe it.
7. **Phoenix** rewrites the harness code itself, tiered and gated so it cannot erode safety.
8. **Crucible** is the scoreboard that Phoenix and Anvil optimize against.
9. **Aegis** ensures Scarlight only acts within authorized scope; enforces air-gapped mode when set.
10. **Lighthouse** records everything so trust is auditable; exports trajectories for training.
11. **Anvil** trains models on Scarlight's verifiable rewards — locally, optionally, or federated.

## The pillar dependency graph

```
                  Phoenix     Anvil
                  (code)    (weights)
                     ↑        ↑
                       Crucible
                       ↑      ↑
                    Codex   Oracle
                    ↑   ↑      ↑
              Mnemos   Hydra ──┘
                         ↑
                       Forge
                         ↑
                      Arsenal
                         ↑
              Aegis ←─ Lighthouse (cross-cuts all)
```

Aegis and Lighthouse cross-cut every pillar. Phoenix mutates code; Anvil produces model weights. Both feed off Crucible's verifiable rewards. The rest form a stack from substrate (Arsenal) to evolution (Phoenix + Anvil).

## Default tech stack per pillar (v0 strawman)

| Pillar | Default implementation |
|--------|------------------------|
| Hydra | LiteLLM-style gateway; vLLM/SGLang for local (`devstral-small-2:24b` / `gemma4:31b` / `Qwen3-32B` / `Foundation-Sec-8B` / `Qwen3-235B-A22B` / `GLM-4.5-Air` / `WhiteRabbitNeo-V2-70B`); Anthropic/OpenAI/Google APIs for `cloud`/`hybrid` modes; Ollama / MLX for laptop tier |
| Forge | Python asyncio coordinator + worker, Redis/SQLite for journal; CodeModeSubagent for code-heavy missions |
| Arsenal | Firecracker MicroVMs via Arrakis-style controller; OCI tool image (incl. coding toolchain: git, LSPs, AFL++, libFuzzer, pwntools, radare2, ghidra, …); MCP servers per tool; coding sub-mode toolbox |
| Codex | Python skills + SQLite + pgvector for retrieval; git for versioning; canary pipeline |
| Mnemos | SQLite FTS5 + DuckDB for analytics + KuzuDB embedded for target graph |
| Oracle | Per-skill `verify()` methods + shared verifier toolbox (HTTP timing, DNS callback, file hash, OPA, Semgrep, KubeLinter, custom) |
| Phoenix | Python orchestrator; archive in git; tiered mutations (T0–T3); CoT-monitor; population provenance |
| Crucible | Docker-Compose-based scenario runner; per-task SQLite results DB; `verifiers`-compatible Env exports |
| Aegis | Rust gateway daemon, Ed25519 contracts, JWT capability tokens, sops-encrypted vault, four deployment-mode enforcement |
| Lighthouse | OpenTelemetry SDK + Langfuse (self-hosted) + append-only signed JSONL; sanitized trajectory export for Anvil |
| Anvil | `prime-rl` (default) / `verl` / `OpenRLHF`; `verifiers` environments; GRPO/DAPO/GSPO; federated-gradient client |

# ADR 0006 — Local-first; frontier-augment optional; air-gapped mode supported

**Status:** Accepted
**Date:** 2026-05-13
**Refines:** Pillar 1 (Hydra) and Pillar 9 (Aegis) in [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Context

Open question: how does Scarlight handle local hosting / on-prem / air-gapped use?

Empirical context:

- **Pentesting engagements frequently require on-prem deployment.** Customer data, source code, and infrastructure access cannot leave the customer's premises. This is the dominant deployment shape for serious engagements.
- **TrustedSec's 2026 benchmark** showed self-hosted models are *competitive* on common offensive tasks: `gemma4:31b` 98.5%, `devstral-small-2:24b` 95.6% on Juice Shop SQL/JWT/LFI/IDOR with 22.9s latency and 2,651 tokens. Smaller, focused models with good harness scaffolding outperformed larger generic models.
- **Multi-step exploits scored 0%** across local models on advanced tasks — *harness scaffolding* (planner/summarizer, target graph, retrieval) is what closes the multi-step gap, not bigger models.
- **TGI is in maintenance mode** since December 2025; vLLM and SGLang are the production-grade self-hosted inference engines.
- **Foundation-Sec-8B** (Cisco / FoundationAI) is an 8B Llama-derived security-specific model surpassing Llama 3.1-70B and WhiteRabbitNeo-V2-70B on CTIBench-RCM — proves small specialized models are viable.
- **The "local LLM security paradox"** (Quesma): local models comply with malicious prompts at up to 95% rate. This is a feature for offensive work and a risk for defensive use — Aegis must mediate.
- **Frontier models still meaningfully outperform locals on novel reasoning** (RiskInsight 2026). For top-tier capability, frontier API access matters.

## Decision

**Local-first as the default. Frontier-augment is opt-in. Air-gapped mode is supported as a first-class Aegis configuration.**

### Three deployment modes

| Mode | Network | Models | Use case |
|------|---------|--------|----------|
| `air_gapped` | None — Aegis blocks all external egress *including model APIs*. Telemetry off. | Local only (vLLM/SGLang/llama.cpp/Ollama/MLX) | Customer-premises pentest, sensitive engagement, classified networks |
| `local_default` | Egress allowlisted to scoped target only. No model APIs by default. | Local for all roles | Default privacy posture |
| `hybrid` | Local for tactical; frontier API for strategic planning. Operator-opt-in per engagement. | Local + frontier (Claude/GPT/Gemini) | Best capability when no data-residency constraint |
| `cloud` | Egress unrestricted (still scope-enforced for *targets*). All providers available. | Any | CTF, training, bug-bounty against publicly-scoped targets |

### Mode is encoded in the engagement contract

The signed engagement contract names the mode. Aegis enforces it at the gateway. Switching modes mid-engagement requires a new signed contract.

### Local model tiering (the recommendations)

Based on TrustedSec 2026 + Foundation-Sec-8B benchmarks + community Qwen3/GLM/DeepSeek availability:

| Tier | Model | Use | Hardware |
|------|-------|-----|----------|
| **Workhorse** | `devstral-small-2:24b` | Default for tactical reasoning, summarization, tool-call repair | 1× 48GB GPU or 64GB RAM CPU-only |
| **High-accuracy** | `gemma4:31b` | Planner, complex reasoning, when latency tolerable | 1× 80GB GPU |
| **Domain-tuned** | `Foundation-Sec-8B` (Cisco/FoundationAI) | CTI, vulnerability classification, threat-intel tasks | 1× 24GB GPU |
| **Open frontier-class** | `Qwen3-235B-A22B`, `DeepSeek-R1`, `GLM-4.5-Air` | Strategic planner equivalent to frontier API | 8× H100 or shared cluster |
| **Coding sub-mode** | `qwen3-coder:30b`, `devstral-small-2:24b`, or `Qwen3-Coder-480B-A35B` | Code-mode subagent (exploits, fuzzers, PoCs) | varies |
| **Offensive-tuned (legacy OSS)** | `WhiteRabbitNeo-V2-70B` | When you specifically want offensive-tuned (uncensored) behavior | 1× 80GB GPU |

Notes on missing models:
- **`Deep Hat`** (Kindo's successor to WhiteRabbitNeo) is proprietary as of 2026. Scarlight does not require it.
- **`Lily-Cybersecurity`** has limited documented capability evidence; not in default recommendations.

### Inference engine

- **Default: vLLM.** Broadest hardware support, biggest community, OpenAI-compatible endpoint.
- **Alternative: SGLang.** ~29% higher throughput at small model scale; better for multi-turn / prefix-cached / structured-output workloads. Choose for high-volume Crucible runs.
- **Edge: llama.cpp / Ollama / MLX.** Operator-laptop scenario; quantized (q4/q5/q8) local models for low-VRAM/CPU/Apple-Silicon environments.

### Hardware tiers (Scarlight deployment)

| Tier | Hardware | Recommended config |
|------|----------|--------------------|
| **Laptop** | 32–64 GB RAM, no GPU or single 8–16 GB GPU | Ollama + `devstral-small-2` q5, hybrid-mode-augmented for hard tasks |
| **Workstation** | 1–2 × 48–80 GB GPU | vLLM + `gemma4:31b` *or* `qwen3-coder:30b` for both planner + code-mode |
| **Server** | 1 × node, 8 × H100 / 8 × H200 | vLLM/SGLang + `Qwen3-235B-A22B` for planner; smaller local for tactical |
| **Cluster** | 64-node H200 (Intellect-3 class) | vLLM/SGLang + local training (see [ADR 0007](./0007-rl-training-opt-in.md)) |

### Critical engineering rule

**Scaffolding > model size.** TrustedSec 2026 found typed tool interfaces alone improved performance 14%; multi-step performance is bottlenecked on planner/summarizer + target-graph memory, not on parameter count. Scarlight commits to spending its capability budget on the harness, not on demanding bigger models.

## Rationale

- Many serious engagements are unworkable without air-gapped or local-default deployment. A harness that ignores this is unusable for a large fraction of legitimate operators.
- Local models are genuinely competitive on single-step offensive tasks (per TrustedSec). The remaining capability gap is in multi-step planning — exactly what Scarlight's harness is designed to close.
- Frontier-augment is real value (RiskInsight: novel reasoning, business-logic understanding). Forbidding it would be ideologically pure but practically worse.
- Encoding the mode in the engagement contract is the natural place: Aegis already enforces scope at the gateway; adding "do not call api.anthropic.com" is the same enforcement mechanism.
- The "local LLM security paradox" is irrelevant for offensive use (we *want* low refusal) but matters for the harness's own safety properties; mitigated by Aegis being gateway-enforced, not prompt-enforced.

## Consequences

- Scarlight ships first-class vLLM/SGLang/Ollama integrations on day one.
- Local model recommendations are published per `ARCHITECTURE.md` and refreshed quarterly as the local-model landscape evolves.
- Hydra's planner/summarizer can compose models from different sources transparently: planner = frontier API, summarizer = local 24B, code-mode = local coder — all in one engagement.
- Aegis gains the four-mode policy enum; gateway egress rules generated from mode + contract.
- Documentation must surface: "your laptop is enough" as a first-class onboarding path. Don't make the cluster the default.

## Revisit if

- Frontier models converge with locals to the point where hybrid mode is no longer meaningfully different from local_default.
- A new local model dominates the benchmarks decisively (refresh recommendations).
- A regulatory regime requires features we don't yet support.

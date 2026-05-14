# ADR 0004 — Code-fluent, not a coding harness

**Status:** Accepted
**Date:** 2026-05-13
**Supersedes:** Implicit "Scarlight ≠ Claude Code" framing in [`ARCHITECTURE.md`](../ARCHITECTURE.md) — clarified here.

## Context

Open question raised: should Scarlight *be* a coding harness (Claude Code / OpenCode / OpenHands category) since exploits, payloads, PoCs, fuzzers, deobfuscators, and tooling are all *code* — or should it be something else?

Empirical pressure on this question:

- **BSidesSF 2026** result is unambiguous: Claude Code + Codex solved *every* challenge, including binary exploitation. 16 teams fully solved all challenges, up from "most unsolved" the prior year. A `--dangerously-skip-permissions` Claude Code run inside a VM with Ghidra + Playwright + Conda was sufficient.
- **Raptor** (`gadievron/raptor`) proves a coding harness (Claude Code) can be *specialized* into an offensive-security agent via `CLAUDE.md` + sub-agents (offsec, crash-analysis, forensics) + skills + tool orchestration (Semgrep, CodeQL, AFL++).
- **TrustedSec's 2026 benchmark** found "scaffolding matters more than size — typed tool interfaces alone improved performance 14%."
- **`verifiers` v0.1.12** explicitly upstreamed an **OpenCode CLI harness** as a first-class environment harness.

These signals say: **a competent coding harness already gets you 60–80% of the way to a competent offensive-security agent.**

## Decision

**Scarlight is code-fluent, not a coding harness.**

Specifically:
1. Scarlight's workers can enter a **code-mode subloop**: write exploits, compile binaries, run fuzzers, debug PoCs, drive a debugger. Code is a *means*, not the *deliverable*.
2. The **deliverable** is a finding with a proof-of-exploit (Oracle). Not a PR.
3. Scarlight does **not** inherit coding-harness primitives that conflict with offensive use:
   - No "respect repository conventions" prompting.
   - No "run the test suite as the primary success signal" — Oracle's exploit verifier is the success signal.
   - No "open a PR" — engagement reports are the artifact.
4. Scarlight **does** inherit coding-harness primitives that help:
   - File-system as durable scratch (Anthropic harness guidance).
   - Git for engagement-side artifact versioning.
   - LSP for fast symbol navigation when reading target source (whitebox).
   - Test-runner as one signal among many in `lab`/CTF mode.
5. **Embedding pattern.** When a skill needs heavy code work (e.g., synthesize a ROP chain, write a deserialization gadget, build a wasm module), the Forge worker spawns a *code-mode subagent* with a coding-tuned model (devstral, qwen-coder, or frontier coding model) and a coding-tool MCP bundle. The subagent's output is verified by Oracle and returned.
6. **Interoperability.** Scarlight workers can be invoked *from* a coding harness (Claude Code, OpenCode) via MCP — Scarlight ships as an MCP server that exposes engagement primitives. This means: a security engineer working in Claude Code can call into Scarlight for offensive operations without leaving their editor.

## Rationale

- The CTF evidence says coding harnesses are sufficient for CTF-scale offensive work. Forking that capability into Scarlight is wasteful.
- The *delta* between a coding harness and a serious offensive-security harness is: scope enforcement (Aegis), target-graph memory (Mnemos), deterministic finding validation (Oracle), payload-class governance (Aegis), engagement reporting (Lighthouse). These are what Scarlight adds.
- A coding harness is the wrong shape for `red_team` or `pentest` engagements where the deliverable is a *report* and the workflow lasts days/weeks/months, not minutes.
- Conversely, building Scarlight as a coding harness commits to repo-shaped UX and signals — wrong for the operator persona.
- The **code-mode subloop** captures coding capability without committing to coding-harness shape.

## Consequences

- Arsenal's tool image includes coding-tier tools (git, build chain, LSPs for target languages, debuggers, fuzzers — pwntools, AFL++, libFuzzer, honggfuzz). This was already implied; now explicit.
- Hydra's model-tiering rule: coding-heavy tasks route to a coding-tuned model (frontier coding model in `cloud` mode; devstral-small-2 / qwen-coder in `local`/`air_gapped` mode).
- Forge gains an explicit `CodeModeSubagent` worker class.
- Scarlight ships an MCP server so external coding harnesses (Claude Code, OpenCode, Codex CLI) can invoke Scarlight primitives. Two-way interop, not a fork.

## Revisit if

- The coding-harness ecosystem absorbs the Aegis/Oracle/Mnemos primitives natively (unlikely; their UX is wrong for engagement work).
- A specific class of engagement reveals that code-mode subloop is insufficient and we need a deeper coding-harness embedding.

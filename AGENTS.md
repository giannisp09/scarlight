# AGENTS.md — Scarlight repository agent context

> This file is the standing context for any agent acting on the Scarlight repository itself (Claude Code, OpenCode, Codex, Aider, …). It is the project-local entry point. Read it, then read `specs/`.

---

## What this repository is

Scarlight is an open-source, self-improving agent for offensive security, built by forking and adapting [`nousresearch/hermes-agent`](https://github.com/nousresearch/hermes-agent). It re-aims a proven self-improving general-purpose agent at authorized offensive-security work — penetration testing, bug bounty, CTF, red-team operations, and security research.

v1 is **deliberately lean**: fork hermes-agent, rebrand it, re-aim its skills and tools at offensive security, add a minimal authorization guard, and get it completing one real engagement end-to-end. That is the whole of v1 — nothing more is committed scope.

---

## Source of truth: read `specs/` first

**`specs/` is the committed source of truth.** Read it before doing anything else, in this order:

1. [`specs/mission.md`](./specs/mission.md) — the *why*: what Scarlight is, who it's for, what v1 is and is not.
2. [`specs/tech-stack.md`](./specs/tech-stack.md) — the *technical decisions*: what the hermes-agent fork keeps / changes / removes / adds.
3. [`specs/roadmap.md`](./specs/roadmap.md) — the *phases in order*: Phase 0 (fork & rebrand), Phase 1 (adapt to offensive security), and a deferred architecture revisit.
4. [`specs/fork-runbook.md`](./specs/fork-runbook.md) — the *operational procedure*: the concrete, step-ordered runbook you actually execute.

Supporting context:

- [`README.md`](./README.md) — the project pitch.
- [`CODE_OF_USE.md`](./CODE_OF_USE.md) — the Authorized Use Policy. Non-negotiable for contributors and operators.

---

## `specs/` vs `docs/` — `docs/` is parked

`docs/` contains an earlier architecture exploration — an 11-pillar design, ADRs, a threat model. It is **parked: reference only, not v1 scope.** It does not drive v1 and must not be built toward unless it is explicitly revived during the (deferred) architecture revisit.

**If `specs/` and `docs/` disagree, `specs/` wins.** Do not treat the 11 pillars, the pillar package names (Hydra, Forge, Aegis, …), the Rust/WASM language split, or the ADRs as current commitments — they belong to the parked exploration.

---

## Current repository state

**Phase 0 complete; Phase 1 in progress.** The `hermes-agent` fork has landed and been rebranded — fork-runbook Steps 1–2 are done: the SDD product layer landed on top of upstream `hermes-agent` (history intact), the repo relicensed to Apache-2.0 with a `NOTICE` retaining hermes-agent's MIT attribution, and `hermes` → `scarlight` rebranded throughout (`scarlight_cli/`, the `scarlight` entry point, `~/.scarlight/`, package name, imports, config paths).

The codebase is now **hermes-agent's module layout, rebranded** — `agent/`, `providers/`, `plugins/`, `environments/`, `skills/`, `tools/`, `scarlight_cli/`, `gateway/`, `docker/`, and so on — *not* the 11-pillar package layout from `docs/`. See [`specs/tech-stack.md`](./specs/tech-stack.md) for each module's fate (keep / re-aim / dormant / remove). Layered on top is Scarlight's own product layer:

```
AGENTS.md        — this file
README.md        — project pitch
CODE_OF_USE.md   — Authorized Use Policy
LICENSE          — Apache-2.0
NOTICE           — hermes-agent MIT attribution (Scarlight is a derivative work)
specs/           — committed SDD product layer (source of truth)
docs/            — parked 11-pillar architecture exploration (reference only)
examples/        — reference engagement configs
```

**Next:** fork-runbook Steps 3–9 — Phase 1: trim to the offensive surface, re-aim the skill library and tool layer at offensive security, verify the self-improving core, add the authorization guard, and drive one engagement end-to-end.

---

## How to contribute (agent edition)

If you are an agent acting on this repo:

1. **Read `specs/` before acting.** It is the source of truth. When in doubt, defer to it.
2. **v1 is fork-and-adapt, not greenfield.** Keep hermes-agent's module layout and its mechanisms. Re-aim *content* (skill seeds, tool wrappers); do not re-architect the engine.
3. **Do not invent architecture.** The 11-pillar design is parked. If something does not fit v1's lean scope, it is deferred to the architecture revisit — note it, don't build it. No new subsystems.
4. **Follow the fork-runbook order.** The steps are sequenced for a reason. In particular: the authorization guard (Step 7) lands *before* offensive tooling is live end-to-end (Step 8). Scarlight must never have offensive tooling live without an authorization check on the path.
5. **Keep the self-improving core functionally unchanged.** `agent/`, `memory/`, `providers/`, `plugins/`, `environments/` get rebrand-level edits only. The skill-creation / memory loop is the reason to fork — do not break it.
6. **Re-aim skills and tools, don't re-mechanize them.** Replace general-purpose skill seeds with offensive-security seeds; add offensive tooling through the existing tool dispatch. The storage / creation / refinement *mechanism* stays as-is.
7. **`gateway/` stays dormant.** Keep the messaging connectors in the tree with their dependencies as an optional extra. Do not wire `gateway/` into any engagement path.
8. **Prefer editing existing files.** `specs/` is intentionally lean; new top-level documents need justification. Once Phases 0–1 are done, per-feature specs land as `specs/NNNN-<feature>/` directories.

---

## House style

- Documents are Markdown, soft-wrapped (no hard wraps at 80 cols).
- Tables for comparison, prose for reasoning, bullets for enumeration.
- Cite prior art explicitly. If you copy a pattern, name the source.
- One sentence in the README is worth a page in the docs. Be tight.
- Edits to `specs/` are product-layer changes — treat them with the weight that implies. They are the committed plan, not scratch notes.

---

## Don'ts

Drawn from [`specs/roadmap.md`](./specs/roadmap.md) non-goals and [`CODE_OF_USE.md`](./CODE_OF_USE.md):

- Do not build toward the parked 11-pillar architecture in `docs/`.
- Do not introduce new languages, runtimes, or build systems beyond hermes-agent's existing toolchain in v1.
- Do not introduce a closed-source dependency on the critical path.
- Do not make a capability cloud-only or SaaS-only. Scarlight is OSS-first; every capability must run locally.
- Do not add offensive tooling without the authorization guard in place on the engagement path.
- Do not wire `gateway/` (messaging connectors) into any engagement path.
- Do not write skills or tools that target specific real-world organizations.
- Do not write skills for CVEs that are not publicly disclosed, or for autonomous 0-day weaponization.
- Do not ship a default skill library targeting OT / ICS / medical devices — those are gated, opt-in only, never default.

---

## v1 technical shape

Full detail is in [`specs/tech-stack.md`](./specs/tech-stack.md). In brief:

- **Toolchain:** Python 3.11+, `uv`, Node.js — the standard hermes-agent toolchain. No new languages or runtimes in v1.
- **Tool protocol:** MCP (Model Context Protocol) — inherited from hermes-agent, kept.
- **Skill format:** `agentskills.io`-compatible — inherited, kept. Rebrand paths, not the format.
- **Rebrand:** `hermes` → `scarlight` throughout — the `scarlight` entry point, `hermes_cli/` → `scarlight_cli/`, `~/.hermes/` → `~/.scarlight/`, package names, imports, config paths.
- **Execution:** offensive tools run via hermes-agent's existing Docker backend with a Kali-style image — no new sandbox substrate.
- **Authorization guard:** a scope/authorization config file plus a pre-flight check — a config and a check, not a subsystem.

---

## How to read the codebase

The fork has landed. `specs/` remains the source of truth for *intent* — what v1 is and is not — but the codebase itself is now hermes-agent's, rebranded.

The entry points are hermes-agent's, rebranded: the `scarlight` CLI in `scarlight_cli/`, the agent loop in `agent/`, the skill library in `skills/`, the tool layer in `tools/`, memory in `plugins/memory/`. The parked `docs/` paths (`scarlight/forge/…`, `scarlight/aegis/…`, etc.) do not exist and will not — they describe the parked design, not v1.

# Tech Stack

> Scarlight v1 is a fork of `nousresearch/hermes-agent`. The tech stack *is* hermes-agent's tech stack, minus the chatbot surface, plus an offensive-security surface. This document records what we inherit and what we change.

---

## Foundation

| Property | Value |
|----------|-------|
| Base project | [`nousresearch/hermes-agent`](https://github.com/nousresearch/hermes-agent) |
| Base license | MIT |
| Languages | Python (~88%) · TypeScript (~8.8%) · Shell, Nix |
| Python | 3.11+ |
| Package manager | `uv` |
| Structure | Modular — pluggable subsystems, not monolithic |
| Tool protocol | MCP (Model Context Protocol) — inherited, kept |
| Skill format | `agentskills.io`-compatible — inherited, kept |

We do not introduce new languages, runtimes, or build systems in v1. The standard hermes-agent toolchain (`uv`, Python 3.11+, Node.js, ripgrep, ffmpeg) is the Scarlight v1 toolchain.

## Inherited modules

hermes-agent's top-level directories and what v1 does with each:

| hermes-agent dir | v1 action | Notes |
|------------------|-----------|-------|
| `agent/` | **Keep** | Core agent loop — the reasoning cycle. Carries over unchanged. |
| `memory/` | **Keep** | FTS5 session search, LLM summarization, Honcho user modeling. The self-improving memory — kept as-is. |
| `providers/` | **Keep** | Model-agnostic LLM provider abstraction. Kept; ensures Scarlight stays provider-neutral. |
| `plugins/` | **Keep** | Extension system + MCP integration. Kept. |
| `environments/` | **Keep (deferred use)** | Atropos RL training environments. Not exercised in v1, retained for later. |
| `docker/` | **Keep, adapt** | Container configs — the base for an offensive tool image. |
| `skills/` | **Re-aim** | Replace general-purpose skill seeds with offensive-security skill seeds. |
| `tools/` | **Re-aim** | Add offensive tooling through the existing tool dispatch; trim general-purpose tools that don't serve offensive work. |
| `hermes_cli/` | **Rebrand** | → `scarlight_cli/`. The TUI/CLI scaffold is kept; names change. |
| `web/` | **Keep, defer** | Dashboard backend. Not a v1 priority; left in place. |
| `gateway/` | **Keep (dormant)** | Messaging-platform connectors (Telegram, Discord, Slack, etc.). Not wired into v1; dependencies moved to optional extras. Available later for notifications / remote approvals. |
| `website/` | **Remove** | Hermes's documentation site. Replaced with Scarlight's own docs later. |

## What we keep

The reason to fork rather than greenfield — these carry over with minimal or no change:

- **The agent loop** (`agent/`) — the core reason-act cycle.
- **The self-improving core** — autonomous skill creation, skill refinement during use, the "closed learning loop."
- **Memory** (`memory/`) — FTS5 session search, summarization, Honcho operator modeling.
- **Provider abstraction** (`providers/`) — model-agnostic; works across frontier and local models.
- **Plugin + MCP integration** (`plugins/`) — extensibility surface.
- **RL environments** (`environments/`) — kept for a possible later training path; unused in v1.
- **Messaging connectors** (`gateway/`) — kept dormant: dependencies made optional, not wired into any engagement path. Retained because long-running engagements benefit from a notification / remote-approval channel; deleting working modular code would be the non-lean move.

## What we change

- **`skills/` → offensive-security skills.** The skill library is re-seeded for recon, web exploitation, and similar offensive tasks. The *mechanism* (how skills are stored, created, refined) is unchanged; the *content* is re-aimed.
- **`tools/` → offensive tooling.** Offensive tools (e.g. recon and web-testing utilities) are added through the existing tool dispatch. General-purpose tools that don't serve offensive work are trimmed.
- **CLI rebrand.** `hermes_cli/` → `scarlight_cli/`; the `hermes` entry point → `scarlight`; `~/.hermes/` → `~/.scarlight/`; package names, imports, and config paths follow.

## What we remove

- **`website/`** — Hermes's docs site.
- **General-purpose tools** from `tools/` that have no offensive-security use.

(Note: `gateway/` is *not* removed — see "What we keep". It is kept dormant with optional dependencies.)

## What we add (v1, minimal)

- **Offensive skill seeds** — a starter set of offensive-security skills.
- **Offensive tool wrappers** — offensive tooling registered through the existing tool layer; v1 runs them via hermes-agent's existing Docker execution backend with a Kali-style image.
- **A minimal authorization guard** — a scope/authorization config file and a pre-flight check that runs before any engagement. This is intentionally small: a config + a check, not an architectural subsystem. It exists because Scarlight is an offensive tool and acting without an authorization check would be irresponsible.

## Licensing

- **Hermes attribution.** hermes-agent is MIT-licensed. A `NOTICE` file retains the MIT copyright notice and license text for the forked code.
- **Scarlight's own license.** **Apache-2.0 — confirmed.** Scarlight v1 ships under Apache-2.0; the direction originated in `docs/decisions/0001-license-apache-2.md`. MIT-forked code combines into an Apache-2.0 project provided the MIT notice is retained — which is the purpose of the `NOTICE` file. The repo's `LICENSE` is Apache-2.0, and `README.md` and `CODE_OF_USE.md` state the same.

## Deferred (explicitly out of v1)

These were part of the parked `docs/` architecture exploration. They are **not** v1 tech-stack commitments:

- Additional languages or runtimes (e.g. a Rust trust path).
- Heavy sandbox substrates (MicroVMs / Firecracker).
- A deterministic finding-validation system.
- A separate scope-enforcement trust domain.
- An evaluation harness.
- Harness-level self-modification.

If and when the architecture is revisited, these are candidates — but only after v1 is running and there are real learnings. See [`roadmap.md`](./roadmap.md).

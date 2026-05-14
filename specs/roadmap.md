# Roadmap

> v1 is deliberately lean: fork hermes-agent and adapt it into a working offensive-security agent. This file is the single source of truth for the roadmap. The operational detail for Phases 0–1 lives in [`fork-runbook.md`](./fork-runbook.md).

---

## Phase 0 — Fork & rebrand

**Goal:** a clean Scarlight fork that builds and runs, with Hermes branding gone.

- Fork `nousresearch/hermes-agent`.
- Add a `NOTICE` file with the Hermes MIT attribution; ship under Apache-2.0 (confirmed — see [`tech-stack.md`](./tech-stack.md)).
- Rebrand `hermes` → `scarlight` throughout: entry points, `hermes_cli/` → `scarlight_cli/`, `~/.hermes/` → `~/.scarlight/`, package names, imports, config paths.

**Exit criteria:**
- The repo builds (`uv sync`).
- `scarlight --help` runs.
- No `hermes` branding remains in user-facing surfaces (grep-clean).
- `LICENSE` is Apache-2.0 and `NOTICE` correctly attributes the MIT-licensed origin.

## Phase 1 — Adapt to offensive security

**Goal:** Scarlight completes one simple engagement end-to-end.

- **Trim to the offensive surface** — remove `website/` and general-purpose tools; leave `gateway/` (messaging connectors) dormant, with its dependencies as optional extras and no engagement path wired to it.
- **Re-aim the skill library** — seed `skills/` with offensive-security skills (recon, web exploitation, etc.).
- **Re-aim the tool layer** — wire offensive tooling through the existing tool dispatch; run it via the existing Docker backend with a Kali-style image.
- **Keep the self-improving core verified** — confirm `agent/`, `memory/`, `providers/`, `plugins/`, `environments/` still work after the changes; the skill-creation / memory loop must still run.
- **Add a minimal authorization guard** — a scope/authorization config file and a pre-flight check before any engagement.
- **End-to-end bring-up** — pick one simple target (a local CTF challenge or a deliberately-vulnerable lab app) and make `scarlight` complete it end-to-end.

**Exit criteria:**
- `scarlight` completes a simple engagement against an authorized lab/CTF target, start to finish.
- The authorization guard blocks an engagement when no valid scope config is present.
- The self-improving loop demonstrably produced or refined at least one skill during the run.
- `gateway/` is dormant — no engagement path invokes it, and its dependencies are excluded from the default install.

## Later — Architecture revisit (deferred)

After v1 is real and there are learnings from running it, the broader architecture is re-planned. Open questions parked until then: deterministic finding-validation, scope-enforcement as a separate trust domain, an evaluation harness, harness-level self-modification, heavier sandboxing.

The earlier 11-pillar exploration in `docs/` is **parked reference material** — it may or may not inform the revisit. It is not committed scope and should not be built toward unless explicitly revived.

---

## Non-goals (any version)

- Autonomous 0-day weaponization for undisclosed CVEs.
- A default skill library targeting OT / ICS / medical devices (gated, opt-in only — never default).
- Closed-source dependencies on the critical path.
- A SaaS-only product. Scarlight is OSS-first; every capability must run locally.

## Release cadence

- Phase 0 and Phase 1 ship as tagged milestones.
- Cadence beyond v1 is set during the architecture revisit, not before.

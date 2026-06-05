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
- The authorization guard enforces scope when an `engagement.yaml` is present, and refuses a *present-but-invalid* one. Engagements are **opt-in** (revised 2026-06-05): a session with no `engagement.yaml` runs unscoped rather than being blocked — forcing engagements on every session was rejected as UX friction. Operator responsibility under `CODE_OF_USE.md` is the load-bearing frame in every mode.
- The self-improving loop demonstrably produced or refined at least one skill during the run.
- `gateway/` is dormant — no engagement path invokes it, and its dependencies are excluded from the default install.

## Phase 2 — Active exploitation (v1.1)

**Goal:** Scarlight completes a full kill-chain engagement (recon → exploitation → post-exploitation → flag) on an authorized target.

- Ship Tier 1 (initial access): `web-exploit`, `password-attack`, `service-exploit`, `payload-craft`.
- Ship Tier 2 (post-exploitation): `privesc-linux`, `privesc-windows`, `credential-harvest`.
- Ship connect-and-confirm `lateral-movement` (pulled forward from v1.2 Tier 3 — scope-limited: single pivot per invocation, no spraying / relay / recursive auto-pivot / persistence).
- Add `risk_level` frontmatter convention on all skills (documentation-only enforcement in v1.1; engine-side gate is a follow-up spec).
- Add audit-log helper and the JSONL audit trail at `~/.scarlight/audit/exploitation.jsonl`.
- Document the `engagement.yaml` `permitted_risk_level` extension (parser implementation is follow-up; backward-compatible until then).
- Tighten `--no-scope` behavior for exploitation skills (skill-body banner in v1.1; CLI-side routable-IP heuristic is follow-up).
- Codify the conventions in `skills/offensive/CONVENTIONS.md` (re-validation pattern, audit-log helper, stop-condition expectations, idempotency, sandbox-by-default, authorized-use anchor).

**Exit criteria:**
- All eight new skills (seven Tier 1+2 plus `lateral-movement`) appear in `skills_list` output.
- End-to-end test passes on at least one full kill-chain target (HackTheBox Starting Point / Metasploitable / DVWA chain) AND a two-host lab demonstrating the connect-and-confirm pivot.
- Every exploitation invocation produces an audit-log entry with the §5.3 schema from [`exploitation-v1/requirements.md`](./exploitation-v1/requirements.md).
- [`mission.md`](./mission.md) non-goals still honored (no autonomous 0-day, no default OT/ICS, no closed-source on the critical path, no SaaS dependency).
- Phase 1 fork-runbook verification gates still green (no regression).

**Deferred to v1.2+:**
- Tier 3 (AD): `ad-recon`, `ad-attack`. `lateral-movement` pulled forward into v1.1 (connect-and-confirm scope only — full multi-hop / spraying / relay variants remain v1.2+).
- Tier 4 (specialized surfaces): `wireless-attack`, `cloud-attack`, `mobile-attack`, `container-escape`.
- `password-spray`, `ntlm-relay`, recursive auto-pivot, port-forwarding / SOCKS proxy substrate — separate v1.2 specs.
- Engine-side `risk_level` enforcement (skill-load filter + per-invocation gate).
- Interactive `msfconsole` sessions (need a session-management substrate).
- C2 / implant frameworks (Sliver, Mythic, Havoc) — indefinitely deferred.
- EDR / AV evasion engineering — indefinitely deferred.

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

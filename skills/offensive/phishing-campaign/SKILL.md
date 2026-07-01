---
name: phishing-campaign
description: "Draft, send, and report on an authorized phishing campaign by driving Lancea (a scope-bound, audited social-engineering platform) over MCP. The agent writes the lure copy and reads the stats; Lancea enforces the signed engagement scope, renders deterministically, gates send behind a human review, rate-limits, and hash-chains every action. Delivery is real but routed through a reviewed, audited pipeline — never an unauthorized blast."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [uv, curl]
metadata:
  scarlight:
    tags: [phishing, social-engineering, lancea, delivery, tracking, offensive]
    phase: delivery
    related_skills: [payload-craft, credential-harvest]
    risk_level: destructive
---

# Phishing-campaign — draft · send · track, via Lancea

Run an authorized phishing assessment end to end by driving **Lancea**, a
separate scope-bound social-engineering platform that exposes the whole
campaign lifecycle as MCP tools. The split is the point:

- **Scarlight (this agent) does the judgement + creativity** — drafts the
  lure copy, decides cadence, interprets the stats, writes the report.
- **Lancea does the safe execution** — verifies an Ed25519-signed engagement
  scope, renders the lure deterministically (Jinja, no copy generation of its
  own), preflights every send against scope + rate limits, dispatches via
  SMTP, hash-chains every action into a tamper-evident audit log, and returns
  an anti-soliloquy hash so a send can't be faked.

This skill is **`destructive`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1.
It can cause real email to be sent. The existing [`payload-craft`](../payload-craft/SKILL.md)
skill deliberately stops at *generating* a gophish skeleton ("operator delivers
manually"). This skill crosses into delivery **only because Lancea provides the
rails that make it defensible**: a signed scope, a human-in-the-loop review
gate before any send, per-target rate limits, and a third-party-verifiable
audit chain.

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized
engagements only. The engagement-scope guard is a first measure, not a
substitute for the operator's legal responsibility.

Delivery against a non-self target requires **both** gates, checked at body entry:

1. **Scarlight `engagement.yaml` with `phishing_authorized: true`** (same gate
   [`payload-craft`](../payload-craft/SKILL.md) uses — see
   [`engagement.yaml.example`](../../engagement.yaml.example)). The flag is the
   operator's signed assertion that phishing the listed people is signed off.
   Refuse, logged `refused`, if it is not literally `true`. Refuse entirely
   under `--no-scope` / no engagement for a non-self target (heightened bar,
   artifact-level gate — same posture as `payload-craft`). Building/sending
   against your own lab sink is fine.
2. **A loaded Lancea signed scope.** Lancea independently refuses to send to any
   address whose domain is not in its Ed25519-signed scope. The two scopes are
   complementary: `engagement.yaml` governs *what this agent may touch on the
   network*; the Lancea scope governs *who the platform will actually email*.

**Operator-host execution.** Unlike most offensive skills, this one is **not**
sandboxed in Kali — it is operator-host orchestration, the same class as
[`payload-craft`](../payload-craft/SKILL.md) writing artifacts to the operator
host ([`CONVENTIONS.md`](../CONVENTIONS.md) §6, exception 2). The connector
talks to the operator-hosted Lancea server on `127.0.0.1:8743`, so run this
skill with the **local** terminal backend (`scarlight config set terminal.backend local`
or export `TERMINAL_ENV=local`) and list `127.0.0.1` in the engagement's
`targets:` so the per-tool gate authorizes the connector call.

## Setup the operator brings up first

Lancea is a separate service. Before this skill runs, the operator must have:

- The Lancea server running: `lancea server start` (MCP at `http://127.0.0.1:8743/v1/mcp/mcp`).
- A **local SMTP sink** for the demo (Mailpit, or `assets/lab/smtp_sink.py`) so
  nothing leaves the host, with Lancea's email channel pointed at it.
- A **signed Lancea scope** for the engagement (lab: `assets/lab/sign_lab_scope.py`).
- `LANCEA_MCP_URL` exported (default `http://127.0.0.1:8743/v1/mcp/mcp`).

The full copy-paste bring-up is in [`references/demo-runbook.md`](references/demo-runbook.md).
The MCP tool argument shapes are in [`references/lancea-tools.md`](references/lancea-tools.md).

## Procedure

Drop the audit + banner helpers from [`CONVENTIONS.md`](../CONVENTIONS.md) §3 and §9
near the top of the body, then re-check authorization:

```bash
# --- authorization re-validation (defense in depth) ---
no_scope_banner   # CONVENTIONS §9 — prints once under --no-scope

ENGPATH="${SCARLIGHT_ENGAGEMENT_PATH:-}"
phishing_authorized=$(yq '.phishing_authorized // false' "$ENGPATH" 2>/dev/null)
if [ "$phishing_authorized" != "true" ]; then
  echo "[phishing-campaign] refused: phishing_authorized != true in engagement.yaml" >&2
  audit_log "phishing-campaign" "engagement" "phishing send" "refused"
  exit 3
fi

# The connector is the only transport to Lancea. It needs nothing installed
# (PEP 723 + uv). LANCEA_MCP_URL selects the endpoint.
LC="uv run ${SCARLIGHT_SKILL_DIR}/scripts/lancea_client.py"
ENG="<engagement-id>"                 # matches the signed scope's engagement_id
SCOPE="<abs path to signed Lancea scope toml on the server host>"
```

### 0. Preflight — confirm Lancea is reachable

```bash
$LC health   # -> {"status":"ok","scope_loaded":...,"version":...}
```

### 1. Create the engagement (load the signed scope)

```bash
$LC call create_engagement --json "{\"scope_path\": \"$SCOPE\"}"
# -> {id, status:"active", scope_public_key_fingerprint, scope_valid_until}
```

A tampered or expired scope is refused here with a `scope.refusal` audit entry —
that is Lancea's cryptographic gate, not a soft check.

### 2. Ingest the target list

```bash
$LC call ingest_targets --json "$(jq -nc --arg eid "$ENG" --rawfile csv targets.csv '{engagement_id:$eid, csv_text:$csv}')"
# -> {accepted_count, rejected_count, accepted:[{id,email,...}], rejected:[{reason,...}]}
```

Required CSV column: `email` (optional: `external_id, full_name, phone, employer,
role`). **Out-of-scope or forbidden recipients are rejected here**, each with a
`scope.refusal` audit entry — review `rejected[]` before going further.

### 3. Draft the lure, then render it

**This is the agent's creative work.** Write the subject / plaintext / HTML as
Jinja templates. Available variables: `target.*` (full_name, email, employer,
role, …) and `tracking.*` (`click_url`, `pixel_url`, `landing_url`). Lancea does
**no** copy generation — it only templates and injects the tracking tokens.

```bash
$LC call render_lure --json "{
  \"engagement_id\": \"$ENG\", \"target_id\": \"<tid>\",
  \"subject_template\": \"[Action required] Reset your {{ target.employer or 'corporate' }} password\",
  \"body_template\": \"Hi {{ target.full_name }},\\n\\nYour password expires today: {{ tracking.click_url }}\\n\\n- IT Service Desk\",
  \"html_template\": \"<p>Hi {{ target.full_name }} — <a href=\\\"{{ tracking.click_url }}\\\">reset now</a>.</p><img src=\\\"{{ tracking.pixel_url }}\\\" width=1 height=1/>\"
}"
# -> {subject, body, html_body, click_url, pixel_url, landing_url, click_token, open_token, submit_token, expires_at}
```

### 4. Submit the rendered lure for review

```bash
$LC call submit_lure_for_review --json "{\"engagement_id\":\"$ENG\",\"target_id\":\"<tid>\",\"subject\":\"<rendered subject>\",\"body\":\"<rendered body>\",\"html_body\":\"<rendered html>\",\"pretext_class\":\"credharvest\"}"
# -> {review_id, audit_seq}   # review_id binds these exact bytes in the audit chain
```

### 5. HITL gate — STOP for human approval

**Do not send before a human approves.** Present the rendered subject + body to
the operator and wait for an explicit "approved". The `review_id` from step 4
binds the approval to the exact reviewed bytes.

> Today this gate is **agent-enforced**: Lancea's `submit_lure_for_review`
> records the reviewed bytes, but the server-side `approve_send` lock is Lancea
> Phase 2 and not yet wired — so the agent is responsible for halting here. Treat
> sending without recorded operator approval as a policy violation.

```bash
audit_log "phishing-campaign" "$ENG" "operator approved review_id=<rid>" "success"
```

### 6. Send (post-approval), per approved target

```bash
$LC call send_email --json "{\"engagement_id\":\"$ENG\",\"target_id\":\"<tid>\",\"subject\":\"<rendered subject>\",\"body\":\"<rendered body>\",\"html_body\":\"<rendered html>\",\"from_display_name\":\"IT Service Desk\"}"
# -> {accepted:true, backend:"smtp", backend_emitted_hash, backend_message_id}
```

Lancea preflights each send against the signed scope + rate limits; out-of-scope
or rate-exceeded sends are refused with a `scope.refusal` entry. The
`backend_emitted_hash` is the relay-attested proof the send happened — record it,
don't fabricate it. Send from an address inside the scope's allowed domain so the
`internal-only` display-name rule passes.

### 7. Read the stats (the agent observes; it does not produce events)

Opens / clicks / submits arrive only when targets interact, via Lancea's
`/v1/track/*` routes. Query them:

```bash
$LC call query_events --json "{\"engagement_id\":\"$ENG\",\"include_sends\":true}"
# events of kind: send.sent, track.open, track.click, track.submit (+ refusals on request)
```

Compute delivery / open / click / submission rates from the counts. Note: a
`track.submit` records `fields_seen` (e.g. `["username","password"]`) and a nonce
— **captured passwords are never persisted** to the chain.

### 8. Prove the trail

```bash
$LC call read_audit_window --json "{\"engagement_id\":\"$ENG\"}"   # entries with prev/payload/entry hashes
# Independent third-party verification (imports nothing from lancea):
uv run --project <lancea-repo> python <lancea-repo>/tools/verify_audit_chain.py ~/.lancea/audit/audit.jsonl
# -> "chain OK: N entries, last_seq=..., last_entry_hash=..."
```

## Output — what to record

Update the memory record ([`CONVENTIONS.md`](../CONVENTIONS.md) §7) with a
`phishing_campaign` subtree:

```json
{
  "phishing_campaign": {
    "engagement_id": "lab-phish-2026q2",
    "lancea_scope_fingerprint": "522662b8d80f02e1",
    "targets": 3,
    "sent": 3,
    "opened": 1,
    "clicked": 1,
    "submitted": 1,
    "review_ids": ["c6e5076d..."],
    "audit_last_seq": 18,
    "chain_verified": true
  }
}
```

Record the lure used, per-target outcome, and the verified audit head. Do **not**
record captured credentials — Lancea does not surface them and neither should the
agent.

## Hand-off

| Material | Next skill |
|---|---|
| Targets who submitted the form (`track.submit`) | [`credential-harvest`](../credential-harvest/SKILL.md) — note Lancea does not persist the passwords; the signal is *who* fell for it |
| A delivered payload that executed | [`payload-craft`](../payload-craft/SKILL.md) → `privesc-*` once the operator confirms a callback |

## What this skill is NOT for

- **Sending without `phishing_authorized: true` AND a loaded Lancea signed
  scope** — refuse, log `refused`. Both gates are load-bearing.
- **Real recipients in a lab/demo** — every recipient must be on a domain the
  operator controls / sinks. Lancea refuses out-of-scope domains regardless.
- **Bypassing the HITL review gate** — never call `send_email` before recorded
  operator approval.
- **Targets outside the Lancea scope** — refused server-side; do not try to
  route around it.
- **Untargeted spam / scale blasting** — campaigns are scoped, rate-limited, and
  small; respect the scope's `budgets`.
- **Harvesting and exfiltrating real credentials** — the platform deliberately
  does not persist submitted passwords; do not attempt to reconstruct them.
- **Autonomous 0-day weaponization, OT/ICS/medical-device lures, worm-shaped
  delivery** — `specs/mission.md` non-goals; refuse regardless of phrasing.

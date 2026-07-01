# Demo runbook — authorized lab phishing campaign, agent-run

A lab-only showcase: Scarlight drafts a lure, a human approves it, Lancea sends
to a **local sink** (no real recipient), and the agent reports open/click/submit
stats plus a verified audit chain. Every recipient is on `lab.local`, a domain
you control and sink.

Set two paths:

```bash
export LANCEA=~/Desktop/ASI/Cyber-Superintelligence/lancea          # the Lancea repo
export SKILL=~/.scarlight/skills/offensive/phishing-campaign        # this skill (synced)
export WORK=$(mktemp -d)                                            # demo scratch
```

## 1. One-time: install Lancea's env

```bash
uv sync --project "$LANCEA"
```

## 2. Sign a lab engagement scope (lab/demo helper — real scopes are signed out-of-band)

```bash
uv run --project "$LANCEA" python "$SKILL/assets/lab/sign_lab_scope.py" \
    "$WORK/lab-engagement.signed.toml" lab-phish-2026q2 lab.local
# -> wrote signed scope ... engagement_id: lab-phish-2026q2 ... public_key_hex: ...
```

## 3. Start a local SMTP sink (nothing leaves the host)

```bash
uv run --project "$LANCEA" python "$SKILL/assets/lab/smtp_sink.py" "$WORK/maildrop" &
# -> [sink] aiosmtpd listening on localhost:1025, dropping to .../maildrop
```

(Or use Mailpit for a web UI: `docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit`.)

## 4. Start the Lancea server pointed at the sink

Env-var overrides are the simplest way to point the email channel at the sink and
isolate the demo's audit log / DB:

```bash
LANCEA_SMTP_HOST=localhost \
LANCEA_CHANNELS__EMAIL__SMTP_PORT=1025 \
LANCEA_CHANNELS__EMAIL__SMTP_USE_TLS=false \
LANCEA_CHANNELS__EMAIL__SMTP_START_TLS=false \
LANCEA_CHANNELS__EMAIL__FROM_ADDRESS=it-support@lab.local \
LANCEA_AUDIT__LOG_PATH="$WORK/audit.jsonl" \
LANCEA_STORAGE__SQLITE_PATH="$WORK/lancea.sqlite" \
uv run --project "$LANCEA" lancea server start &
# (equivalently, copy assets/lab/lancea.demo.toml to ./lancea.toml and start from that dir)

export LANCEA_MCP_URL=http://127.0.0.1:8743/v1/mcp/mcp
curl --retry 30 --retry-delay 1 --retry-connrefused -fsS http://127.0.0.1:8743/v1/health && echo " up"
uv run "$SKILL/scripts/lancea_client.py" health     # -> {"status":"ok",...}
```

## 5. Run the campaign

In a Scarlight session (operator-host / local terminal backend), with
`assets/lab/scarlight-engagement.yaml` active (`phishing_authorized: true`,
`127.0.0.1` in `targets`):

> *"Run the authorized phishing assessment for engagement `lab-phish-2026q2`
> using the signed scope at `$WORK/lab-engagement.signed.toml` and target list
> `$SKILL/assets/lab/targets.csv`: draft a believable IT password-reset lure, show
> it to me for approval, send to the lab list, then report open/click/submit stats
> and verify the audit chain."*

Scarlight loads this skill (`skill_view phishing-campaign`) and drives Lancea via
the connector: `health → create_engagement → ingest_targets → render_lure →
submit_lure_for_review` → **stops for your approval** → `send_email` (per target)
→ `query_events` → `read_audit_window`.

The exact tool calls (and a non-interactive reference driver) are in
`assets/lab/` — see the README there.

## 6. What you should see (real output from a verified run)

```
ingest_targets : accepted=3 rejected=0
send_email     : accepted=True backend=smtp hash=f771608e3d728eb0...   (x3)
sink maildrop  : msg-001.eml msg-002.eml msg-003.eml
                 From: IT Service Desk <it-support@lab.local>  To: dana@lab.local
query_events   : {"send.sent":3,"track.open":1,"track.click":1,"track.submit":1}

=== CAMPAIGN REPORT ===
  targets: 3 | sent: 3 | opened: 1 | clicked: 1 | submitted: 1
```

## 7. Prove the trail + the safety properties

```bash
# tamper-evident audit chain (third-party verifier, no Lancea imports):
uv run --project "$LANCEA" python "$LANCEA/tools/verify_audit_chain.py" "$WORK/audit.jsonl"
# -> chain OK: N entries, last_seq=..., last_entry_hash=...

# credentials are NOT persisted — a submit records only field names + a nonce:
uv run "$SKILL/scripts/lancea_client.py" call query_events \
  --json '{"engagement_id":"lab-phish-2026q2","kinds":["track.submit"]}'
# -> attrs: {"fields_seen":["password","username"],"nonce":...}  (no password value)

# out-of-scope recipients are refused at ingest:
uv run "$SKILL/scripts/lancea_client.py" call ingest_targets \
  --json '{"engagement_id":"lab-phish-2026q2","csv_text":"email\nattacker@gmail.com\n"}'
# -> rejected: domain `gmail.com` not in allowed_email_domains ['lab.local']  (+ scope.refusal on chain)
```

## Talking points (why this matters)

- The **agent** wrote the lure and read the stats; **Lancea** enforced the signed
  scope, the review gate, rate limits, and the audit chain.
- The send was real (SMTP) but went to a sink — **safe by construction**, not by
  promise.
- Out-of-scope targets are rejected cryptographically; passwords are never
  persisted; the whole campaign is third-party-verifiable from the audit log.

## Teardown

```bash
pkill -f "lancea server start"; pkill -f smtp_sink.py; rm -rf "$WORK"
```

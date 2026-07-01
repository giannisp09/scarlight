# Lancea MCP tool cheat-sheet

The connector (`scripts/lancea_client.py`) carries one tool call over MCP.
Invoke as `uv run scripts/lancea_client.py call <tool> --json '<args>'`. Every
tool except `health` takes its arguments under a single `payload` model — the
connector wraps `--json` into `{"payload": ...}` for you, so pass the **inner**
object shown below.

Endpoint: `$LANCEA_MCP_URL` (default `http://127.0.0.1:8743/v1/mcp/mcp` — Lancea
mounts FastMCP's default `/mcp` path under `/v1/mcp`, hence the doubled segment).

| Tool | Args (inner JSON) | Returns |
|---|---|---|
| `health` | *(none)* | `{status, scope_loaded, version, audit_last_seq}` |
| `create_engagement` | `{scope_path, engagement_id?}` — path is resolved **on the server host** | `{id, scope_engagement_id, scope_public_key_fingerprint, scope_valid_until, status, created_at}` |
| `load_scope` | `{scope_path}` — verify + summarize, no persist | `{engagement_id, authorizing_organization, allowed_email_domains, enabled_channels, max_targets, ...}` |
| `list_engagements` | `{status?, limit?}` | list of engagement records |
| `get_engagement` | `{engagement_id}` | one engagement record |
| `ingest_targets` | `{engagement_id, csv_text}` — CSV requires `email`; optional `external_id, full_name, phone, employer, role`; extras kept | `{accepted_count, rejected_count, accepted:[{id,email,...}], rejected:[{row_index,reason,offending_target}]}` |
| `list_targets` | `{engagement_id}` | list of target records |
| `get_target_dossier` | `{target_id}` | one target record + `extra` |
| `render_lure` | `{engagement_id, target_id, subject_template, body_template, html_template?, variables?, token_ttl_days?}` — Jinja; vars `target.*` + `tracking.*` | `{subject, body, html_body, click_url, pixel_url, landing_url, click_token, open_token, submit_token, expires_at}` |
| `submit_lure_for_review` | `{engagement_id, target_id, subject, body, html_body?, pretext_class?}` | `{review_id, audit_seq}` — `review_id` binds the exact bytes |
| `send_email` | `{engagement_id, target_id, subject, body, html_body?, from_address?, from_display_name?, correlation_id?}` | `{accepted, backend, backend_message_id, backend_emitted_hash, correlation_id, sent_at, error?}` |
| `query_events` | `{engagement_id?, target_id?, start_seq?, limit?, kinds?, include_refusals?, include_sends?}` | `{events:[{seq,ts,kind,engagement_id,target_id,attrs}], next_seq}` |
| `read_audit_window` | `{start_seq?, end_seq?, limit?, engagement_id?}` | `{entries:[{seq,ts,kind,attrs,prev_hash,payload_hash,entry_hash}], last_seq, chain_last_seq}` |

## Notes that bite

- **No `verify_chain` MCP tool.** Chain verification is the standalone script
  `tools/verify_audit_chain.py LOG.jsonl` in the Lancea repo (imports nothing
  from Lancea). The default audit log is `~/.lancea/audit/audit.jsonl` unless
  `LANCEA_AUDIT__LOG_PATH` overrides it.
- **Event kinds:** `query_events` defaults to `track.click|track.open|track.submit`.
  Pass `include_sends:true` for `send.sent|send.failed`, `include_refusals:true`
  for `track.refusal|scope.refusal`-style entries.
- **Telemetry is observe-only.** `record_open/click/submit` are NOT MCP tools —
  events are produced by HTTP hits on `pixel_url` (open), `click_url` (click),
  and `POST /v1/track/submit/<submit_token>` (submit). The agent reads them back
  via `query_events`; it cannot fabricate them.
- **HITL:** `submit_lure_for_review` only records the reviewed bytes (Phase 1.3).
  The server-side `approve_send` lock is Lancea Phase 2 — until then the agent
  must halt for operator approval before `send_email`.
- **Streaming resources** (snapshot reads): `events://engagements/{id}/clicks`,
  `events://engagements/{id}/submits`.

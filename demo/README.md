# Scarlight v1.1 — recordable kill-chain demo

A self-contained, ~7-minute demo that showcases the v1.1 active-exploitation bundle end-to-end against a two-container Linux lab:

1. **Scope guard refuses** an engagement with no `engagement.yaml` on file (Step 7).
2. **Operator drops the scope** (`demo/engagement.yaml`) and we read it aloud — two targets now, web-target and pivot-target.
3. **Lab spins up** — both containers built from local Dockerfiles, bound to host loopback.
4. **The engagement runs** — `scarlight chat -q` streams the agent's tool calls and reasoning. Every shell command executes inside a freshly-launched **Kali sandbox**, not the operator's host.
5. **Full kill chain** — recon → web-exploit (command injection on `/ping`) → credential-harvest (steal `/root/.ssh/id_rsa`) → **lateral-movement** (ssh into pivot-target with the stolen key) → trophy (`cat /root/flag.txt`).
6. **The agent teaches itself a new skill** — capturing the recognizable signature of this chain so future engagements against similar targets start smarter.
7. **Teardown** — both containers + the private network removed.

Built for **terminal recording** (asciinema / OBS / screen capture). Each act has a colored banner so the recording has natural beats.

---

## What's new in v1.1 (vs the original 3-min v1 demo)

| Aspect | v1 demo | v1.1 demo |
|---|---|---|
| Lab | One container (Juice Shop) | Two containers — web-target + pivot-target on a private bridge network |
| Skills exercised | `recon`, `web-basic` | Full v1.1 bundle: `recon`, `web-basic`, `web-exploit`, `credential-harvest`, `lateral-movement`, plus an autonomously-created chain skill |
| Narrative arc | Passive recon + fingerprinting | Full kill chain — initial access → post-exploitation → authorized pivot → trophy |
| Headline beat | "The agent wrote its own skill" | "The agent stole a key on host A and pivoted to host B, then wrote a skill capturing the pattern" |
| Runtime | ~3 min | ~7 min |
| Audit log | Not shown | Surfaced at the end as proof-of-chain (JSONL entries for each skill invocation) |

The v1.1 demo preserves every v1 narrative beat (scope-guard refusal, operator authorization, sandbox-by-default, autonomous skill creation) and extends them with the new exploitation surfaces.

---

## Prereqs

- Docker Desktop (or any Docker daemon) running, with the `docker compose` plugin (v2).
- An inference provider key configured — OpenRouter is the path of least friction; see `scarlight status` to confirm.
- `scarlight` on `PATH`. The repo's venv install puts the binary at `.venv/bin/scarlight`; symlink it into a directory on your `PATH`:
  ```bash
  ln -sf "$(pwd)/.venv/bin/scarlight" ~/.local/bin/scarlight
  ```
- ~200 MB total for the two lab images on first run (python:3.11-slim + alpine:3.20). Cached after.

---

## Run it

From the repo root:

```bash
demo/run.sh
```

That single command drives the entire demo end-to-end. Flags:

| Flag | What it does |
|------|-------------|
| `--no-refusal`  | Skip Act 1 (the scope-guard refusal beat). |
| `--no-teardown` | Leave both lab containers running after the demo. |

Environment knobs:

| Var | Default | Notes |
|-----|---------|------|
| `SCARLIGHT_DEMO_MODEL`    | `anthropic/claude-sonnet-4.6`     | Any model your provider serves. Sonnet 4.6 is the verified pick — strong enough to drive the chain cleanly. Weaker models may get stuck on the base64 exfiltration step. |
| `SCARLIGHT_DEMO_PROVIDER` | `openrouter`                      | Switch to `anthropic`, `nous`, etc. if you have direct creds. |

---

## Lab — what's running

```
            ┌─────────────────────────┐         ┌────────────────────────┐
operator    │  scarlight-demo-        │         │  scarlight-demo-pivot  │
loopback ──▶│  web-target             │         │                        │
127.0.0.1   │  Flask /ping            │         │  alpine + sshd         │
            │  command injection      │         │  trusts the planted    │
:8080       │  plants /root/.ssh/     │  ssh    │  ssh key               │
            │  id_rsa with admin      │ ──────▶ │                        │
            │  notes pointing at      │         │  /root/flag.txt        │
            │  the pivot host         │         │  ← TROPHY              │
            └─────────────────────────┘         └────────────────────────┘
                                                          ▲
                                                  127.0.0.1:2222
```

Both containers also live on a private bridge network (`scarlight-demo-lab`) so they can reach each other directly, but the agent in the Kali sandbox reaches them via host loopback (`host.docker.internal:8080` and `host.docker.internal:2222`).

The vulnerability and the credential path are baked into the lab Dockerfiles, not into the Scarlight agent — the agent has to find both.

---

## What to record (recording cues)

Total run time: ~7 minutes on Sonnet 4.6 + warm container images.

| Beat | When | What's on screen | Voiceover hook |
|------|------|------------------|----------------|
| **Hook**         | 0:00 – 0:15 | Intro banner | "Scarlight is an OSS offensive-security agent that runs a full authorized kill chain — and teaches itself new skills as it goes." |
| **Refusal**      | 0:15 – 0:35 | Red error from scarlight, refusing to start without a scope | "Every engagement starts with an authorization check. With no `engagement.yaml` on file, Scarlight refuses." |
| **Scope file**   | 0:35 – 0:55 | engagement.yaml printed in full | "Here's the scope. Two targets — a web-target with a known injection bug, and an SSH pivot host. Operator acknowledgment recorded." |
| **Lab up**       | 0:55 – 1:20 | docker compose building both containers | "Two purpose-built Linux containers. Nothing's pre-cracked — the agent has to find the path." |
| **Recon + WX**   | 1:20 – 2:30 | Agent fingerprints web-target, finds `/ping`, confirms injection | "Recon. Then web-exploit. The /ping endpoint takes a host parameter and pipes it into a shell — classic command injection. The agent confirms it." |
| **Credential harvest** | 2:30 – 3:45 | Agent reads /root/notes.txt, base64s /root/.ssh/id_rsa, decodes locally | "Now post-exploitation. The agent finds admin notes pointing at a pivot host, and a private SSH key planted for that host. Reads both through the injection. Notice the base64 — that's the agent picking a reliable exfiltration encoding for a multi-line file." |
| **Lateral move** | 3:45 – 4:30 | `lateral-movement` skill, ssh -i to pivot-target, `id; hostname; cat /root/flag.txt` | "Lateral movement. The stolen key authenticates to the pivot host. Connect-and-confirm — `id`, `hostname`, trophy, and out. No interactive shell, no persistence, no recursion to a third host." |
| **Trophy**       | 4:30 – 5:00 | Flag printed, operator-side verification | "Trophy captured. The flag is the engagement's success signal." |
| **Audit trail**  | 5:00 – 5:45 | tail of `exploitation.jsonl` showing entries for each skill | "Every active and destructive skill invocation wrote an audit-log entry. Auditor can reconstruct the chain in seconds." |
| **Skill saved**  | 5:45 – 6:30 | "Act 6 · payoff" banner with frontmatter of the new skill | "And — the agent wrote its own skill capturing this target's signature. Next time anyone runs Scarlight against a similar setup, this loads automatically." |
| **Outro**        | 6:30 – 7:00 | "Demo complete" + repo URL | "OSS, Apache-2.0. v1.1 closes the chain — initial access, post-ex, authorized lateral movement." |

### Recording with asciinema

```bash
asciinema rec demo.cast --command "demo/run.sh"
# Upload to asciinema.org or convert to GIF/MP4 with agg / svg-term-cli
```

### Recording with OBS / screen capture

Open a wide terminal (140+ columns), set font 14–16pt, then:

```bash
demo/run.sh
```

The colored banners and `sleep` pauses give your screen recorder natural beats. Stop the recording on the "Demo complete" banner.

---

## Re-running

`demo/reset.sh` removes the autonomously-created skill(s) and truncates the sandbox audit log on each run so each take starts clean. Other skills and session records are left alone.

To inspect what the agent did after a run:

```bash
# Latest session JSON (full transcript)
ls -lt ~/.scarlight/sessions/ | head -3

# Audit trail (canonical host path — bind-mounted out of the sandbox)
cat ~/.scarlight/audit/exploitation.jsonl | jq .

# The autonomously-created skill
ls ~/.scarlight/skills/offensive/ | grep -E '(nettools|chain)'
```

Note: as of `engagement_scope._persist_engagement_audit_trail()`, the audit log is bind-mounted out of the Kali sandbox to the canonical host path `~/.scarlight/audit/exploitation.jsonl`, and each line is stamped with the engagement_id / scope reference. (This resolved Finding #2 from `memory/project_exploitation_v1_smoke_findings.md`, which had the log landing in the sandbox overlay.)

---

## File map

| File | Purpose |
|------|---------|
| `run.sh`               | One-button driver. The thing you record. |
| `engagement.yaml`      | The authorization scope file the demo loads — two targets. |
| `prompt.txt`           | The engagement prompt passed to `scarlight chat -q`. |
| `docker-compose.yml`   | Two-container lab definition (web-target + pivot-target). |
| `start-lab.sh`         | `docker compose up -d --build` and wait for both health checks. |
| `stop-lab.sh`          | `docker compose down -v --remove-orphans`. |
| `reset.sh`             | Remove autonomously-created skills + truncate sandbox audit log. |
| `lab/web-target/`      | Dockerfile, app.py (Flask, command-injectable), notes.txt, id_rsa (planted private key). |
| `lab/pivot-target/`    | Dockerfile, authorized_keys (matches web-target's id_rsa), flag.txt (trophy). |
| `README.md`            | This file. |

---

## Out of scope for this demo

Things v1.1 supports that the demo deliberately *doesn't* showcase to stay under ~7 minutes:

- Windows lateral movement — `lateral-movement` SKILL.md documents `netexec smb`, `impacket-psexec`, `evil-winrm`, pass-the-hash, pass-the-ticket. The demo lab is Linux-only.
- Password attack — the demo's pivot path uses key auth, not a cracked hash. `password-attack` exists; just not exercised here.
- Service exploit — `service-exploit` (msfconsole one-shot) is not needed because the initial access is web. Reserved for future demos against a service-banner target.
- Payload craft — `payload-craft` is generation-only and not needed for the connect-and-confirm chain.
- Resume / `--continue` across sessions.
- The dormant `gateway/` (messaging connectors). v1.1 keeps it parked.

## Out of scope for v1.1 (deferred)

These are explicit v1.2+ deferrals — see `specs/exploitation-v1/requirements.md` §7 + `specs/roadmap.md`:

- AD attacks (Kerberoast, AS-REP, DCSync, NTLM relay).
- Password spraying across a CIDR.
- Recursive auto-pivot (B → C → D).
- Interactive shell sessions held across turns.
- Port forwarding / SOCKS proxy substrate.
- Persistence (cron, scheduled tasks, key plants).
- C2 / implant frameworks (Sliver, Mythic, Havoc).

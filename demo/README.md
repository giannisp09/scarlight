# Scarlight v1 — recordable demo

A self-contained, ~3-minute demo that showcases v1 end-to-end:

1. **Scope guard refuses** an engagement with no `engagement.yaml` on file (Step 7).
2. **Operator drops the scope** (`demo/engagement.yaml`) and we read it aloud.
3. **Lab spins up** (OWASP Juice Shop in Docker on host loopback).
4. **The engagement runs** — `scarlight chat -q` streams the agent's tool calls and reasoning. Commands execute inside a freshly-launched **Kali sandbox** (kalilinux/kali-last-release), not the operator's host, because the engagement guard now defaults `TERMINAL_ENV=docker` when scope is active.
5. **The agent teaches itself a new skill** — `juice-shop-fingerprint` is autonomously written to `~/.scarlight/skills/offensive/`. Every future engagement against Juice Shop starts smarter.
6. **Teardown** — lab container removed.

Built for **terminal recording** (asciinema / OBS / screen capture). Each act has a colored banner so the recording has natural beats.

---

## Prereqs

- Docker Desktop (or any Docker daemon) running.
- An inference provider key configured — OpenRouter is the path of least friction; see `scarlight status` to confirm.
- `scarlight` on `PATH`. The repo's venv install puts the binary at `.venv/bin/scarlight`; symlink it into a directory on your `PATH`:
  ```bash
  ln -sf "$(pwd)/.venv/bin/scarlight" ~/.local/bin/scarlight
  ```
- ~700 MB free for the Juice Shop image on first run (cached after).

---

## Run it

From the repo root:

```bash
demo/run.sh
```

That single command drives the entire demo end-to-end. Flags:

| Flag | What it does |
|------|-------------|
| `--no-refusal`  | Skip Act 1 (the scope-guard refusal beat). ~2 min total. |
| `--no-teardown` | Leave the Juice Shop container running after the demo. |

Environment knobs:

| Var | Default | Notes |
|-----|---------|------|
| `SCARLIGHT_DEMO_MODEL`    | `anthropic/claude-sonnet-4.6`     | Any model your provider serves. Sonnet 4.6 is the verified pick — strong enough to drive autonomous skill creation cleanly. |
| `SCARLIGHT_DEMO_PROVIDER` | `openrouter`                      | Switch to `anthropic`, `nous`, etc. if you have direct creds. |

---

## What to record (recording cues)

Total run time: ~3 minutes on Sonnet 4.6 + a warm Juice Shop pull.

| Beat | When | What's on screen | Voiceover hook |
|------|------|------------------|----------------|
| **Hook**       | 0:00 – 0:15 | Intro banner | "Scarlight is an OSS offensive-security agent that teaches itself new skills mid-engagement. Watch one full engagement, start to finish." |
| **Refusal**    | 0:15 – 0:35 | Red error from scarlight, refusing to start without a scope | "Every engagement starts with an authorization check. With no `engagement.yaml` on file, Scarlight refuses." |
| **Scope file** | 0:35 – 0:55 | engagement.yaml printed in full | "Here's the scope. Authorized target: OWASP Juice Shop, running in Docker on this machine. Operator acknowledgment recorded." |
| **Lab up**     | 0:55 – 1:10 | start-lab.sh banner | "Juice Shop, MIT-licensed, OWASP's deliberately-vulnerable training app. Bound to 127.0.0.1 — no third party is touched." |
| **Engagement** | 1:10 – 2:40 | scarlight tool-call stream — apt install, curl probes, the agent's reasoning | "The terminal tool is now inside Kali, not on the host — the engagement guard sets that. Watch the agent recon, find the open /ftp/ directory and the unauthenticated `/rest/admin/application-configuration` endpoint, and decide what's worth saving." |
| **Skill saved** | 2:40 – 2:55 | "Act 6 · payoff" banner with frontmatter of the new skill | "It just wrote its own skill card. Next time anyone runs Scarlight against a Juice Shop instance, this loads automatically. Strictly more capable than 3 minutes ago." |
| **Outro**      | 2:55 – 3:00 | "Demo complete" + repo URL | "OSS, Apache-2.0, link in bio." |

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

The demo deletes the autonomously-created `juice-shop-fingerprint` skill on each run (via `demo/reset.sh`) so the "agent taught itself a new skill" beat works every time. Other skills and session records are left alone.

To inspect what the agent did after a run:

```bash
ls -lt ~/.scarlight/sessions/ | head -3      # latest session JSON
cat ~/.scarlight/skills/offensive/juice-shop-fingerprint/SKILL.md
```

---

## File map

| File | Purpose |
|------|---------|
| `run.sh`         | One-button driver. The thing you record. |
| `engagement.yaml`| The authorization scope file the demo loads. |
| `prompt.txt`     | The engagement prompt passed to `scarlight chat -q`. |
| `start-lab.sh`   | `docker run` the Juice Shop container, wait for HTTP 200. |
| `stop-lab.sh`    | `docker rm -f` the Juice Shop container. |
| `reset.sh`       | Delete the previously-created `juice-shop-fingerprint` skill so the next run shows fresh skill creation. |
| `README.md`      | This file. |

---

## Out of scope for this demo

Things v1 supports that the demo deliberately *doesn't* showcase to stay under 3 minutes:

- Active exploitation (SQLi, XSS, auth bypass) — the demo stops at recon.
- The full ~2000-test suite, the autonomous skill-refinement loop (a re-run on a fresh target *refines* the existing skill — already exercised in the Step 8 verification runs but skipped here).
- Resume / `--continue` across sessions.
- The dormant `gateway/` (messaging connectors). v1 keeps it parked.

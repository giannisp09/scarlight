# Fork Runbook

> The concrete, step-ordered procedure for turning a `hermes-agent` fork into Scarlight v1. This is the operational companion to [`roadmap.md`](./roadmap.md) Phases 0–1. Each step has actions and a check. Do them in order — Step 7 (authorization guard) must land before Step 8 (offensive tools live end-to-end).

Commands below are templates; paths assume the fork is cloned to `scarlight/` (the codebase, alongside the existing `docs/` and `specs/`).

---

## Step 1 — Fork & licensing

**Actions**
- Fork `nousresearch/hermes-agent` on GitHub, then clone your fork.
- Add a `NOTICE` file containing hermes-agent's MIT copyright line and full MIT license text, noting Scarlight is a derivative work.
- Scarlight's own license is **Apache-2.0** — confirmed; see [`tech-stack.md`](./tech-stack.md). Ensure the repo's `LICENSE` file is Apache-2.0. MIT-forked code combines into an Apache-2.0 project as long as the MIT notice is retained — that is the job of the `NOTICE` file above.
- Keep the upstream git history (don't squash) so provenance is auditable.

**Check**
- `NOTICE` exists and contains the MIT text.
- The repo's `LICENSE` file is Apache-2.0.
- `git log` shows upstream history is intact.

## Step 2 — Rebrand

**Actions**
- Rename `hermes_cli/` → `scarlight_cli/`.
- Rename the `hermes` entry point → `scarlight` (check `pyproject.toml` / `[project.scripts]` and any `cli.py` / `run_agent.py`).
- Change the config/state dir `~/.hermes/` → `~/.scarlight/` (including `~/.hermes/skills/` → `~/.scarlight/skills/`).
- Update package names, imports, and string literals: `hermes` → `scarlight`.
- Preserve `agentskills.io` skill-format compatibility — rebrand paths, not the format.

**Check**
- `grep -ri "hermes" --include="*.py" --include="*.toml" --include="*.md" .` returns only intentional references (e.g. the `NOTICE` attribution).
- `uv sync` succeeds.
- `scarlight --help` runs.

## Step 3 — Trim to the offensive surface

**Actions**
- **Leave `gateway/` dormant.** Keep the messaging-platform connectors (Telegram, Discord, Slack, WhatsApp, Signal, Email) in the tree — do not wire them into any engagement path. Move their dependencies into an optional extra (e.g. a `gateway` group under `[project.optional-dependencies]`) so the default `uv sync` does not install them. Keep the `scarlight gateway` entry point, but gated behind that extra. Rationale: long-running engagements benefit from a notification / remote-approval channel later; deleting working modular code is the non-lean move.
- Delete `website/` (Hermes's docs site — replaced by Scarlight's own docs later).
- Trim `tools/`: remove general-purpose tools that have no offensive-security use (keep the tool *dispatch* mechanism).

**Check**
- `website/` is gone; general-purpose tools trimmed.
- `gateway/` still exists, but a default `uv sync` does not install Telegram/Discord/etc. libraries (they live in the optional extra).
- No engagement code path imports or invokes `gateway/`.
- `uv sync` still succeeds; `scarlight --help` still runs.

## Step 4 — Re-aim the skill library

**Actions**
- Clear or archive hermes-agent's general-purpose skill seeds in `skills/`.
- Seed `skills/` with a starter set of offensive-security skills (e.g. basic recon, a simple web-exploitation skill). Keep the set small — v1 only needs enough to run one engagement.
- Do **not** change the skill mechanism (storage, autonomous creation, refinement) — only the seed content.

**Check**
- `skills/` contains offensive-security seeds and no leftover general-purpose ones.
- The skill loader still discovers and lists skills (`scalight`'s skill-list command, whatever Hermes called it, still works after rebrand).

## Step 5 — Re-aim the tool layer

**Actions**
- Register offensive tooling through the existing `tools/` dispatch (the same mechanism Hermes used for its tools).
- For v1 execution, use hermes-agent's existing **Docker terminal backend** with a Kali-style image — do not build a new sandbox substrate.
- Pin the tool image (tag or digest) for reproducibility.

**Check**
- The offensive tools are listed by the tool dispatch.
- A trivial tool invocation runs inside the Docker backend and returns output.

## Step 6 — Keep the core untouched (and verify it)

**Actions**
- Leave `agent/`, `memory/`, `providers/`, `plugins/`, `environments/` functionally unchanged — only rebrand-level edits from Step 2.
- Run a smoke test of the self-improving loop: a short task that should cause a skill to be created or refined.

**Check**
- The agent loop runs end-to-end on a trivial task.
- Memory writes a session record and it is searchable.
- At least one skill is autonomously created or refined during the smoke test.

## Step 7 — Add a minimal authorization guard

> **Must land before Step 8.** Scarlight must never have offensive tooling live without an authorization check.

**Actions**
- Define a simple scope/authorization config file (e.g. `engagement.toml` / `.yaml`): authorized targets, a human-readable authorization reference, and an operator acknowledgment field.
- Add a pre-flight check in the engagement entry path: no valid scope config → refuse to start.
- Keep it minimal — a config file plus a check, not a subsystem.
- Keep `CODE_OF_USE.md` prominent; the guard is a first measure, not a substitute for operator responsibility.

**Check**
- Running an engagement with no scope config is refused with a clear message.
- Running with a valid scope config is allowed.
- The pre-flight check sits on the path *every* engagement entry point goes through.

## Step 8 — End-to-end bring-up

**Actions**
- Stand up one simple authorized target: a local CTF challenge or a deliberately-vulnerable lab app (e.g. running in Docker).
- Write a scope config authorizing that target.
- Run `scarlight` against it and drive one engagement to completion.
- Fix whatever breaks; keep the fixes minimal and in scope.

**Check**
- `scarlight` completes the engagement start-to-finish against the authorized lab target.
- The run produced a session record and at least one skill create/refine event.

## Step 9 — Verification gates

Run before declaring v1 done:

- `uv sync` clean; `scarlight --help` runs.
- `grep -ri "hermes" --include="*.py" --include="*.toml" .` → only the `NOTICE` attribution.
- `website/` gone and general-purpose tools trimmed; `gateway/` retained but dormant — not on any engagement path, and its dependencies are excluded from the default install.
- The authorization guard refuses an engagement with no scope config.
- A full engagement against an authorized lab target completes end-to-end.
- The self-improving loop (skill create/refine + memory) demonstrably ran during that engagement.
- `LICENSE` is Apache-2.0 and `NOTICE` retains the hermes-agent MIT attribution — the two are consistent.

---

When all Step 9 gates pass, Phases 0–1 of [`roadmap.md`](./roadmap.md) are complete. Do not start the architecture revisit until there are real learnings from running v1.

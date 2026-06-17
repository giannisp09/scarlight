# Mission

> **Scarlight is an open-source, self-improving agent for offensive security — built by forking and adapting [`nousresearch/hermes-agent`](https://github.com/nousresearch/hermes-agent).**

Scarlight takes a proven self-improving general-purpose agent and re-aims it at authorized offensive security work: penetration testing, bug bounty hunting, CTF, red-team operations, and security research. It is open source, and it gets better with use because it inherits Hermes's ability to write its own skills and remember across sessions.

---

## The problem

The 2024–2026 offensive-security AI boom produced 70+ open-source agents — CAI, HackSynth, PentestGPT, HackingBuddyGPT, ctf-agent, and more. Almost all of them share the same weakness: they are **shallow model wrappers**. They do not remember what worked last time, they do not accumulate skill, and they start every engagement from zero. An operator who runs one of these tools a hundred times has the same tool on run 100 as on run 1.

The capability that actually compounds — a memory of past engagements and a library of skills that grows and refines itself — exists in general-purpose agents but has not been brought to offensive security in open source.

## Why fork hermes-agent

`hermes-agent` already has the part that is hard to build and rare to find: a **working self-improving core**.

- **Autonomous skill creation** — it writes new skills from experience.
- **Skill self-improvement** — skills get refined during use.
- **Cross-session memory** — full-text session search and a deepening model of the operator.

It is also a clean base to fork: MIT-licensed, modular (not monolithic), and built in a standard stack (Python + TypeScript). Rebuilding that core from scratch would take months and would most likely be worse. The right move is to **fork it and re-aim it** — keep the self-improving engine, swap the general-purpose surface for an offensive-security one.

## Target users

- **Penetration testers** running authorized engagements under a scope agreement.
- **Bug bounty hunters** working within published program rules.
- **CTF competitors** solving challenges on event infrastructure.
- **Red teamers** running authorized adversary-emulation engagements.
- **Security researchers** working in labs and on systems they own.

## What v1 is

A deliberately lean adaptation of hermes-agent:

- **Rebranded** — `hermes` → `scarlight` throughout.
- **CLI-run, not chat-driven** — Scarlight runs from the command line. hermes-agent's messaging-platform connectors are left dormant in v1 (dependencies optional, not wired into any engagement path); they stay available later as a notification / remote-approval channel.
- **Re-aimed** — the skill library is seeded with offensive-security skills; the tool layer is wired with offensive tooling.
- **Guarded** — a minimal authorization check runs before any engagement, because this is an offensive tool.
- **Running** — it completes one simple engagement (a CTF challenge or a deliberately-vulnerable lab app) end-to-end.

That is the whole of v1.

## What v1.1 adds — active exploitation

v1.1 closes the gap between Scarlight's recon-only v1 and a full kill-chain agent. It adds active-exploitation skills (`web-exploit`, `password-attack`, `service-exploit`, `payload-craft`), post-exploitation skills (`privesc-linux`, `privesc-windows`, `credential-harvest`), and a connect-and-confirm `lateral-movement` skill, so Scarlight can complete a full multi-host CTF or pentest engagement — recon → exploitation → post-exploitation → authorized pivot → flag / loot — under authorization. v1.1 introduces a `risk_level` frontmatter convention (`passive | active | destructive`) on all skills as a documentation layer; programmatic enforcement is a follow-up. Every exploitation invocation writes an audit-log entry to `~/.scarlight/audit/exploitation.jsonl`. Operator responsibility under [`CODE_OF_USE.md`](../CODE_OF_USE.md) remains the load-bearing legal frame. AD attacks, password spraying, NTLM relay, wireless, cloud, mobile, and container surfaces are tiered deferrals (see [`exploitation-v1/requirements.md`](./exploitation-v1/requirements.md) §7).

## What v1 is NOT

Explicitly out of scope for v1, deferred and unplanned:

- A broader pillar architecture, deterministic finding-validation systems, a separate scope-enforcement trust domain, an evaluation harness, or harness-level self-modification. An earlier design exploration (the 11-pillar architecture in `docs/`) is **parked** — kept as reference, not committed scope. It may or may not inform a later architecture revisit, *after* v1 is real.
- New languages or runtimes beyond what hermes-agent already uses.
- Heavy sandboxing substrates. v1 uses hermes-agent's existing execution backends.

The point of v1 is to get a working, offensive-security-flavored, self-improving agent into existence — and learn from running it — before designing anything bigger.

## Authorized use

Scarlight is an offensive-security tool. It is for use **only** against systems you are explicitly authorized to test. Use of Scarlight is conditional on the [Authorized Use Policy](../CODE_OF_USE.md). The v1 authorization guard is a minimal, honest first measure — not a substitute for the operator's legal responsibility.

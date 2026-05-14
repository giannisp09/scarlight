# specs/

This folder is Scarlight's **Spec-Driven Development (SDD) product layer** — the committed source of truth for what v1 is and how it gets built. Read it before touching code.

## The files

| File | What it is |
|------|------------|
| [`mission.md`](./mission.md) | The *why* — what Scarlight is, who it's for, what v1 is and is not. Technology-agnostic. |
| [`tech-stack.md`](./tech-stack.md) | The *technical decisions* — what we inherit from the hermes-agent fork, what we keep / change / remove / add. |
| [`roadmap.md`](./roadmap.md) | The *phases in order* — Phase 0 (fork & rebrand), Phase 1 (adapt to offensive security), and a deferred architecture revisit. The single source of truth for the roadmap. |
| [`fork-runbook.md`](./fork-runbook.md) | The *operational procedure* — the concrete, step-ordered runbook for Phases 0–1. |

Read them in that order. `mission.md` and `tech-stack.md` set the frame; `roadmap.md` sequences the work; `fork-runbook.md` is what you actually execute.

## `specs/` vs `docs/`

- **`specs/` (this folder)** — committed, lean, current. The v1 plan. Authoritative.
- **`docs/`** — an earlier architecture exploration (an 11-pillar design, ADRs, threat model). **Parked, not committed scope.** Kept as reference; it does not drive v1. Do not build toward it unless it is explicitly revived during the architecture revisit.

If `specs/` and `docs/` disagree, `specs/` wins.

## What comes next

Once Phases 0–1 are done, downstream per-feature specs land here as `specs/NNNN-<feature>/` directories (e.g. `specs/0001-authorization-guard/`), each reading this product layer for context.

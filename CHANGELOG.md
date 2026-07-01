# Changelog

All notable changes to Scarlight are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-07-01

### Added
- **Benchmarking harness** (`environments/benchmarks/`): a benchmark-agnostic
  harness (adapter protocol, budget + `max_usd` cap, run recorder with the
  `scarlight-bench-v1` schema, runner + CLI, registry, contamination checks,
  reporting, and an Inspect bridge). ExploitGym is refactored onto it, with
  Cybench / XBOW / HTB adapters scaffolded. Ships with a Tier‑0 offline test
  suite (MockAdapter + StubModel doubles) that runs with no LLM or Docker.
  See `specs/benchmarking-harness-v1/`.
- SkyPilot one-command cloud runner for ExploitGym.
- `phishing-campaign` offensive skill.

### Changed
- Langfuse plugin env vars renamed `HERMES_LANGFUSE_*` → `SCARLIGHT_LANGFUSE_*`
  (aligns the plugin with the CLI, which already used the `SCARLIGHT_` prefix).

### Fixed
- Langfuse plugin now guards `set_trace_io`, which was removed in langfuse 3.x,
  so the root span always finalizes and traces form a Session.

### Notes
- The XBOW and HTB benchmark adapters are intentional stubs (`run`/`verify`
  raise `NotImplementedError`) pending live wiring; they are labelled as such.

## [1.0.0] - 2026-06-17

### Added
- First public release. Scarlight is a self-improving, offensive-security-first
  AI agent harness — a fork-and-adapt of
  [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent),
  rebranded and relicensed Apache-2.0 (see `NOTICE`).
- Offensive skill set under `skills/offensive/` (recon, web-exploit,
  privilege-escalation, lateral-movement, password-attack, credential-harvest,
  payload-craft, service-exploit) with a documented `risk_level` taxonomy and
  authorization conventions (`skills/offensive/CONVENTIONS.md`).
- Engagement scope guard (`scarlight_cli/engagement_scope.py`): opt-in
  `engagement.yaml` with a target allowlist, operator acknowledgment, and a
  host-persisted audit trail.
- Authorized Use Policy (`CODE_OF_USE.md`) and security trust model
  (`SECURITY.md`).

[Unreleased]: https://github.com/giannisp09/scarlight/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/giannisp09/scarlight/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/giannisp09/scarlight/releases/tag/v1.0.0

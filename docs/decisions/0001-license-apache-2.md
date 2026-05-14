# ADR 0001 — License: Apache 2.0 with separate Authorized Use Policy

**Status:** Accepted
**Date:** 2026-05-13
**Decision-makers:** Scarlight founder

## Context

Scarlight is an OSS offensive-security tool. Licensing choice is sensitive: too permissive and large clouds vendor it without contributing; too restrictive and adoption suffers. Reference points from prior art:

- **CAI** — dual AGPL/MIT.
- **Metasploit Framework** — BSD-3.
- **sqlmap** — GPLv2.
- **Burp Suite** — closed.
- **nuclei** — MIT.
- **Sigstore, Falco, eBPF projects** — Apache 2.0.

The harness category (Claude Code: source-available; OpenCode: MIT; OpenClaw: MIT; Hermes Agent: open-weights / mixed) is heterogeneous.

## Options considered

1. **Apache 2.0** — permissive, patent grant included, dominant in OSS infra / cloud-native (CNCF default).
2. **MIT** — simpler, but no patent grant.
3. **AGPL-3.0** — copyleft for network use; protects against cloud vendoring; but scares some commercial adopters.
4. **Dual MIT / AGPL** (CAI's choice) — best of both, but adds licensing complexity for contributors.
5. **Custom "ethical source"** (Hippocratic License, SSPL variants) — non-OSI; may damage adoption and create real legal ambiguity.

## Decision

**Apache 2.0** for the harness code. Authorized Use Policy lives separately in [`CODE_OF_USE.md`](../../CODE_OF_USE.md) and is enforced socially, contractually (CLA-equivalent), and through community norms — not as a license clause.

## Rationale

- **Patent grant matters** in security tooling. MIT doesn't have one; Apache does.
- **Apache 2.0 is the OSS infrastructure norm** (Kubernetes, Sigstore, OpenTelemetry, Linkerd, CNCF projects). Aligns with the cloud-native / DevSecOps adopter persona.
- **AGPL would hurt adoption.** Enterprise pentest teams generally cannot use AGPL-licensed code in customer engagements without legal review every time. The friction is real.
- **Custom licenses fragment OSS.** "Ethical" license clauses are legally untested and have hurt projects like RedisVL and ElasticSearch with adopter perception.
- **Ethics is a social problem, not a license problem.** [`CODE_OF_USE.md`](../../CODE_OF_USE.md) is the binding ethical layer; the law of the operator's jurisdiction (CFAA, CMA, equivalents) does the heavy lifting.

## Consequences

- Anyone can fork Scarlight. We accept this.
- Cloud providers can offer hosted Scarlight. We compete on community + skill library + speed of improvement.
- We get the broadest possible adoption among legitimate operators.
- Misuse remains the operator's legal responsibility; the OSS license is not the right venue to prevent it.

## Revisit if

- A cloud provider's hosted Scarlight materially damages the community.
- Community feedback indicates AGPL or dual-licensing would attract more contributors than it loses.
- A widely-adopted "ethical source" license achieves OSI-equivalent legitimacy.

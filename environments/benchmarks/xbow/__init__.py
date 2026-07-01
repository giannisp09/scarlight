"""Scarlight ↔ XBOW benchmark adapter stub (rung ``web-pentest``).

Adapter-only: it proves the protocol spans the ``web-pentest`` rung. The full
suite — per-target web-app containers + a controlled exploit-validation harness —
is deferred to a follow-up spec (``requirements.md`` §7).
"""

from environments.benchmarks.xbow.adapter import XBOWAdapter

# `Adapter` alias so the literal `xbow.Adapter` form (validation.md §6.2) resolves.
Adapter = XBOWAdapter

__all__ = ["XBOWAdapter", "Adapter"]

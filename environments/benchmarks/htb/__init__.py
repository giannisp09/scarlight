"""Scarlight ↔ HTB boot2root adapter stub (rung ``kill-chain``).

Adapter-only: it proves the protocol spans the ``kill-chain`` rung ("just an
IP"). The full suite — network sandbox + VPN authorization + the live-validated
exploitation skills — is deferred to a follow-up spec (``requirements.md`` §7).
"""

from environments.benchmarks.htb.adapter import HTBAdapter

# `Adapter` alias so the literal `htb.Adapter` form (validation.md §6.2) resolves.
Adapter = HTBAdapter

__all__ = ["HTBAdapter", "Adapter"]

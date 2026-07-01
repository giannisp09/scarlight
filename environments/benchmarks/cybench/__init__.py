"""Scarlight ↔ Cybench integration (rung ``ctf``).

Cybench (``andyzorigin/cybench``, MIT) is the first *new* rung the harness adds:
40 professional CTF tasks across 6 domains. Like ExploitGym, Cybench is not
vendored — clone it as a sibling and point the adapter at it for live runs; the
embedded task manifest makes enumeration work offline.
"""

from environments.benchmarks.cybench.adapter import CybenchAdapter

__all__ = ["CybenchAdapter"]

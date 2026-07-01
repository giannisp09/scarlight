"""Benchmark adapter registrations (the named seam, kept out of ``harness/``).

The harness core is benchmark-agnostic by construction (``validation.md`` §6.1):
no module under ``harness/`` may name a benchmark. This module — one level up —
is where the four concrete benchmarks are bound to their registry names and
import paths. Registration is lazy: importing this file does *not* import any
adapter's heavy dependencies (a benchmark SDK, Docker, Inspect); each class is
imported only when its benchmark is actually run.

Importing this module is the single side-effecting step that populates the
registry; the runner does it by name (``importlib.import_module(...)``) so even
the runner stays free of benchmark identifiers.
"""

from __future__ import annotations

from environments.benchmarks.harness.registry import available, register_lazy

# rung: exploit-dev — the existing, working benchmark, refactored onto the protocol.
register_lazy("exploitgym", "environments.benchmarks.exploitgym.adapter:ExploitGymAdapter")
# rung: ctf — first new rung.
register_lazy("cybench", "environments.benchmarks.cybench.adapter:CybenchAdapter")
# rung: web-pentest — adapter stub; full suite deferred (requirements.md §7).
register_lazy("xbow", "environments.benchmarks.xbow.adapter:XBOWAdapter")
# rung: kill-chain — adapter stub; full suite deferred (requirements.md §7).
register_lazy("htb", "environments.benchmarks.htb.adapter:HTBAdapter")


def load_all() -> list:
    """Return the registered benchmark names (registration is import-time)."""
    return available()

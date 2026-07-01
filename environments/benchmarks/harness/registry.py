"""A benchmark-agnostic adapter registry.

This module is the seam that lets the runner resolve ``--benchmark <name>``
without ever naming a benchmark itself (``validation.md`` §6.1). It holds only
the registry *machinery*: concrete benchmarks supply their own name + import
path from outside this package (``environments/benchmarks/adapters.py``).

Registration is *lazy* on purpose: an adapter's heavy dependencies (e.g. a
benchmark SDK, Docker) must not be imported until that benchmark is actually
run, so importing the harness — and the whole Tier 0 test suite — stays free of
them.
"""

from __future__ import annotations

import importlib
from typing import Dict, List, Type

# name -> "module.path:ClassName" (resolved on demand)
_LAZY: Dict[str, str] = {}
# name -> already-imported adapter class
_EAGER: Dict[str, Type] = {}


def register_lazy(name: str, dotted_path: str) -> None:
    """Register ``name`` against a ``"module.path:ClassName"`` import string.

    The target is imported only when :func:`load` / :func:`get_class` is called
    for ``name``.
    """
    if ":" not in dotted_path:
        raise ValueError(f"dotted_path must be 'module:Class', got {dotted_path!r}")
    _LAZY[name] = dotted_path


def register(name: str, cls: Type) -> None:
    """Register an already-imported adapter class directly."""
    _EAGER[name] = cls


def available() -> List[str]:
    """All registered benchmark names, sorted (deterministic)."""
    return sorted(set(_LAZY) | set(_EAGER))


def get_class(name: str) -> Type:
    """Resolve ``name`` to its adapter class, importing lazily if needed."""
    if name in _EAGER:
        return _EAGER[name]
    if name in _LAZY:
        module_path, _, class_name = _LAZY[name].partition(":")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        _EAGER[name] = cls
        return cls
    raise KeyError(f"no benchmark adapter registered as {name!r}; available: {available()}")


def load(name: str, **kwargs):
    """Instantiate the adapter registered as ``name``."""
    return get_class(name)(**kwargs)


def clear() -> None:
    """Drop all registrations (test hygiene)."""
    _LAZY.clear()
    _EAGER.clear()

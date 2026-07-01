"""Make the Tier 0 doubles importable as a bare module under this directory.

The benchmark test tree intentionally has no ``__init__.py`` (matching the rest
of ``tests/``), so an explicit path insert guarantees ``from doubles import ...``
resolves regardless of pytest's import mode or xdist worker layout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

"""
tests/conftest.py
==================
Shared pytest fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so 'config' and 'melvin' are importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

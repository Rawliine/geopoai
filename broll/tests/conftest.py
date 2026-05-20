"""Local pytest config for broll tests.

Adds the repo root to ``sys.path`` (so ``import broll`` and ``import pipeline``
work without installation) and registers custom markers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "network: marks tests that hit external HTTP APIs (deselect with -m 'not network')",
    )

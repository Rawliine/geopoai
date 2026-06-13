#!/usr/bin/env python3
"""Backward-compatible shim — implementation lives in ``map_renderer.runner``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Deprecated (W00): import from ``map_renderer.runner`` or ``map_renderer`` instead.
from map_renderer.runner import render_scene, render_scenes  # noqa: E402

__all__ = ["render_scene", "render_scenes"]


def _cli() -> None:
    from map_renderer.runner import _cli as _runner_cli

    _runner_cli()


if __name__ == "__main__":
    _cli()

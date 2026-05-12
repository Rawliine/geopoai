"""Unified dispatcher. Reads the 'renderer' field and routes to the engine."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def render(scene: dict, clip_name: str) -> Path:
    renderer = scene.get("renderer", "mapbox")
    if renderer == "mapbox":
        from pipeline.render_scene import render_scene
        return await render_scene(scene, clip_name)
    if renderer == "manim":
        from pipeline.render_manim import render_manim
        return await render_manim(scene, clip_name)
    raise ValueError(f"Unknown renderer: {renderer!r}")


def _cli():
    if len(sys.argv) < 3:
        print("usage: python pipeline/render.py <scene.json> <clip_name>")
        sys.exit(2)
    scene = json.loads(Path(sys.argv[1]).read_text())
    out = asyncio.run(render(scene, sys.argv[2]))
    print(out)


if __name__ == "__main__":
    _cli()

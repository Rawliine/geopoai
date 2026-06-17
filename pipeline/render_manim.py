"""Manim engine wrapper. Validates, configures, renders, places output."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "manim"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_QUALITY_PRESETS = {
    "preview": {"pixel_h": 480, "fps": 15},
    "draft": {"pixel_h": 720, "fps": 30},
    "full": {"pixel_h": 1080, "fps": 60},
}

_FORMAT_FRAME = {
    "horizontal": (14.2, 8.0, 16 / 9),
    "vertical": (8.0, 14.2, 9 / 16),
}


def _configure_manim(fmt: str, quality: str, media_dir: Path):
    from manim import config

    frame_w, frame_h, aspect = _FORMAT_FRAME[fmt]
    preset = _QUALITY_PRESETS[quality]

    pixel_h = preset["pixel_h"]
    # libx264 (yuv420p) requires even dimensions
    pixel_w = int(round(pixel_h * aspect / 2)) * 2
    if pixel_h % 2:
        pixel_h += 1

    config.frame_width = frame_w
    config.frame_height = frame_h
    config.pixel_width = pixel_w
    config.pixel_height = pixel_h
    config.frame_rate = preset["fps"]
    config.media_dir = str(media_dir)
    config.disable_caching = True
    config.write_to_movie = True


def render_manim_sync(scene: dict, clip_name: str) -> Path:
    from manim_renderer.schema.validator import validate
    ok, errors = validate(scene)
    if not ok:
        for e in errors:
            print(e, file=sys.stderr)
        raise ValueError(f"Scene failed validation: {len(errors)} error(s)")

    fmt = scene["format"]
    quality = scene.get("quality", "preview")

    media_dir = ROOT / "tmp" / "manim_media" / clip_name
    if media_dir.exists():
        shutil.rmtree(media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)

    _configure_manim(fmt, quality, media_dir)

    from manim_renderer.theme.typography import ensure_fonts

    ensure_fonts()

    from manim_renderer.scene import JSONScene

    JSONScene.scene_data = scene
    scene_obj = JSONScene()
    scene_obj.render()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mp4s = list(media_dir.rglob("*.mp4"))
    if not mp4s:
        raise RuntimeError(f"Manim produced no MP4 in {media_dir}")
    src = max(mp4s, key=lambda p: p.stat().st_mtime)
    dst = OUTPUT_DIR / f"{clip_name}.mp4"
    shutil.copy2(src, dst)
    return dst


async def render_manim(scene: dict, clip_name: str) -> Path:
    return await asyncio.to_thread(render_manim_sync, scene, clip_name)


def _cli():
    if len(sys.argv) < 3:
        print("usage: python pipeline/render_manim.py <scene.json> <clip_name>")
        sys.exit(2)
    scene = json.loads(Path(sys.argv[1]).read_text())
    out = render_manim_sync(scene, sys.argv[2])
    print(out)


if __name__ == "__main__":
    _cli()

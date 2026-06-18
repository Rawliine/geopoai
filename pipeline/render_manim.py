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

# Occupancy sampling rate (Hz) written into layout.json. The scene records a
# snapshot at each composition change; we resample onto this fixed grid.
_LAYOUT_SAMPLE_HZ = 2


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

    # Sidecars consumed by the composition lanes (W15 captions / W16 sound).
    fps = _QUALITY_PRESETS[quality]["fps"]
    _write_events_sidecar(scene_obj, clip_name, fps, dst)
    _write_layout_sidecar(scene_obj, clip_name, fmt, scene, dst)
    return dst


def _write_events_sidecar(scene_obj, clip_name: str, fps: int, mp4_path: Path) -> Path:
    """Write `<clip>.events.json` next to the MP4 from the scene's recorded cue
    stream. Schema: docs/contracts/events.schema.json."""
    doc = {
        "clip_id": clip_name,
        "fps": float(fps),
        "events": list(getattr(scene_obj, "emitted_events", []) or []),
    }
    out = mp4_path.with_suffix(".events.json")
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out


def _resample_snapshots(snapshots, duration: float, hz: int) -> list[dict]:
    """Resample (t, boxes) composition snapshots onto a fixed `hz` grid over
    [0, duration]. Each grid frame holds the latest snapshot at-or-before it
    (a step function), so occupancy is recorded at every solve AND between
    solves at the sample rate."""
    snaps = sorted(snapshots, key=lambda s: float(s[0]))
    if not snaps or float(snaps[0][0]) > 0.0:
        snaps = [(0.0, [])] + snaps
    step = 1.0 / hz
    n = max(1, int(round(max(duration, 0.0) * hz)) + 1)
    frames: list[dict] = []
    si = 0
    for k in range(n):
        tg = round(k * step, 4)
        while si + 1 < len(snaps) and float(snaps[si + 1][0]) <= tg + 1e-9:
            si += 1
        frames.append({"t": tg, "boxes": snaps[si][1]})
    return frames


def _write_layout_sidecar(scene_obj, clip_name: str, fmt: str, scene: dict, mp4_path: Path) -> Path:
    """Write `<clip>.layout.json` next to the MP4 from the scene's occupancy
    snapshots. Schema: docs/contracts/layout.schema.json."""
    duration = float(scene.get("scene", {}).get("duration", 0.0))
    snapshots = list(getattr(scene_obj, "_layout_snapshots", []) or [])
    doc = {
        "clip_id": clip_name,
        "format": fmt,
        "sample_hz": _LAYOUT_SAMPLE_HZ,
        "frames": _resample_snapshots(snapshots, duration, _LAYOUT_SAMPLE_HZ),
    }
    out = mp4_path.with_suffix(".layout.json")
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out


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

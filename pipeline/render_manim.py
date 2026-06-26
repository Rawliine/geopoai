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
    # Long showcase scenes emit 200+ partial movie files (one per play()).
    # Manim's default max_files_cached=100 evicts the oldest partials mid-render,
    # so the final concat is incomplete and the combined movie is truncated.
    # Raise the cap so every partial survives until the final combine.
    config.max_files_cached = 10_000


def _final_movie_path(scene_obj, media_dir: Path) -> Path:
    """Resolve the combined scene movie. Trusts the writer's recorded
    `movie_file_path`; falls back to the newest top-level video (never a
    partial under `partial_movie_files/`)."""
    writer = getattr(getattr(scene_obj, "renderer", None), "file_writer", None)
    recorded = getattr(writer, "movie_file_path", None)
    if recorded is not None and Path(recorded).exists():
        return Path(recorded)
    candidates = [
        p for p in media_dir.rglob("*.mp4")
        if "partial_movie_files" not in p.parts
    ]
    if not candidates:
        raise RuntimeError(
            f"Manim produced no combined MP4 in {media_dir} "
            f"(only partial movie files — the final concat did not run)"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def render_manim_sync(scene: dict, clip_name: str) -> Path:
    if scene.get("escape_hatch"):
        from manim_renderer.escape_hatch.runner import render_escape_hatch_sync
        return render_escape_hatch_sync(scene, clip_name)

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
    # Prefer the writer's canonical combined-movie path; never a partial. The
    # old "newest *.mp4 by mtime" heuristic could grab a stray partial movie
    # file (under partial_movie_files/) when a combine was incomplete, silently
    # copying a few-second clip in place of the full scene.
    src = _final_movie_path(scene_obj, media_dir)
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

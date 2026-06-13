"""W00 map regression: two deterministic renders of the same scene produce matching frames."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def _ffprobe_duration(mp4: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(mp4),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def _extract_frame(mp4: Path, t_sec: float, out_png: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{t_sec:.6f}",
            "-i",
            str(mp4),
            "-vframes",
            "1",
            str(out_png),
        ],
        check=True,
    )


def _mean_abs_rgb_diff(a: Path, b: Path) -> float:
    """Mean absolute difference over all pixels and RGB channels (0–255 scale)."""
    im1 = Image.open(a).convert("RGB")
    im2 = Image.open(b).convert("RGB")
    if im1.size != im2.size:
        raise AssertionError(f"size mismatch {im1.size} vs {im2.size}")
    p1 = im1.tobytes()
    p2 = im2.tobytes()
    n = len(p1)
    return sum(abs(p1[i] - p2[i]) for i in range(n)) / float(n)


@pytest.mark.parametrize(
    "scene_rel",
    [
        "scripts/map/test_scene.json",
        "scripts/map/MA_AG.json",
    ],
)
def test_map_deterministic_frames_match_paired_render(scene_rel: str) -> None:
    """T1–T6 used committed goldens; T7 removed them — compare two fresh deterministic renders."""
    load_dotenv(ROOT / ".env")
    if not os.getenv("MAPBOX_TOKEN"):
        pytest.skip(
            "MAPBOX_TOKEN not set: add project .env with Mapbox token to run live W00 map regression"
        )
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

    from map_renderer.runner import render_scene

    scene_path = ROOT / scene_rel
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    stem = scene_path.stem
    clip_a = f"w00_pair_{stem}_a"
    clip_b = f"w00_pair_{stem}_b"

    out_a = ROOT / "output" / f"{clip_a}.mp4"
    out_b = ROOT / "output" / f"{clip_b}.mp4"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        for p in (out_a, out_b):
            if p.exists():
                p.unlink()

        asyncio.run(render_scene(scene, clip_a))
        asyncio.run(render_scene(scene, clip_b))
        assert out_a.is_file() and out_b.is_file()

        dur_a = _ffprobe_duration(out_a)
        dur_b = _ffprobe_duration(out_b)
        assert abs(dur_a - dur_b) < 0.05, f"duration mismatch {dur_a} vs {dur_b}"

        for i in range(8):
            t = (i + 0.5) / 8.0 * dur_a
            png_a = td_path / f"a_f{i}.png"
            png_b = td_path / f"b_f{i}.png"
            _extract_frame(out_a, t, png_a)
            _extract_frame(out_b, t, png_b)
            mad = _mean_abs_rgb_diff(png_a, png_b)
            assert mad < 2.0, f"{stem} frame {i}: mean abs RGB diff between renders {mad:.4f} >= 2.0"

        for p in (out_a, out_b):
            try:
                p.unlink()
            except OSError:
                pass
        for c in (clip_a, clip_b):
            frames_dir = ROOT / "tmp" / c / "frames"
            if frames_dir.parent.exists():
                shutil.rmtree(frames_dir.parent, ignore_errors=True)

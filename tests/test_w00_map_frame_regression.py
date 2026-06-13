"""W00 map regression: deterministic re-render vs T1 golden PNGs (mean abs RGB diff < 2)."""

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
    "scene_rel,clip,golden_prefix",
    [
        ("scripts/map/test_scene.json", "w00_regolden_a", "w00_golden_a"),
        ("scripts/map/MA_AG.json", "w00_regolden_b", "w00_golden_b"),
    ],
)
def test_map_deterministic_frames_match_golden(scene_rel: str, clip: str, golden_prefix: str) -> None:
    load_dotenv(ROOT / ".env")
    if not os.getenv("MAPBOX_TOKEN"):
        pytest.skip(
            "MAPBOX_TOKEN not set: add project .env with Mapbox token to run live W00 map regression"
        )
    # Cursor/sandbox may inject a stale PLAYWRIGHT_BROWSERS_PATH; force default install lookup.
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

    from map_renderer.runner import render_scene

    scene_path = ROOT / scene_rel
    scene = json.loads(scene_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        out_mp4 = ROOT / "output" / f"{clip}.mp4"
        if out_mp4.exists():
            out_mp4.unlink()

        asyncio.run(render_scene(scene, clip))
        assert out_mp4.is_file(), f"expected MP4 at {out_mp4}"

        dur = _ffprobe_duration(out_mp4)
        golden_dir = ROOT / "tests" / "golden" / "w00"
        for i in range(8):
            t = (i + 0.5) / 8.0 * dur
            new_png = td_path / f"{clip}_f{i}.png"
            _extract_frame(out_mp4, t, new_png)
            gold = golden_dir / f"{golden_prefix}_f{i}.png"
            assert gold.is_file(), f"missing golden {gold}"
            mad = _mean_abs_rgb_diff(new_png, gold)
            assert mad < 2.0, f"{golden_prefix} frame {i}: mean abs RGB diff {mad:.4f} >= 2.0"

        try:
            out_mp4.unlink()
        except OSError:
            pass
        frames_dir = ROOT / "tmp" / clip / "frames"
        if frames_dir.parent.exists():
            shutil.rmtree(frames_dir.parent, ignore_errors=True)

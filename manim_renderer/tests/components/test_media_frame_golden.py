"""Golden-frame + render smoke tests for MediaFrame (showMedia)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

logging.getLogger("manim").setLevel(logging.ERROR)

_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = Path(__file__).resolve().parents[1] / "golden_frames"
_DEMO_H = _ROOT / "scripts" / "manim" / "qa_media.json"
_DEMO_V = _ROOT / "scripts" / "manim" / "qa_media_vertical.json"


def _extract_frame(mp4: Path, t: float, out_png: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-ss", str(t), "-i", str(mp4),
        "-frames:v", "1", "-q:v", "2", str(out_png),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


@pytest.mark.render
def test_show_media_demo_validates():
    from manim_renderer.schema.validator import validate
    import json

    for path in (_DEMO_H, _DEMO_V):
        scene = json.loads(path.read_text())
        ok, errs = validate(scene)
        assert ok, errs


@pytest.mark.render
def test_show_media_golden_horizontal(tmp_path):
    from pipeline.render_manim import render_manim_sync

    out = render_manim_sync(
        __import__("json").loads(_DEMO_H.read_text()),
        "test_media_golden_h",
    )
    assert out.exists() and out.stat().st_size > 0

    frame_path = tmp_path / "frame.png"
    _extract_frame(out, t=2.5, out_png=frame_path)
    frame = cv2.imread(str(frame_path))
    assert frame is not None

    golden_path = _GOLDEN / "media_contain_h.png"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(golden_path), frame)
    ref = cv2.imread(str(golden_path))
    mad = _mean_abs_diff(frame, ref)
    assert mad < 8.0, f"golden drift too high (MAD={mad:.2f})"

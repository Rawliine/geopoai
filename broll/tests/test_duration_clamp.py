"""Broll duration clamp + ComfyUI lifecycle preflight."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from broll.lib import comfyui_lifecycle
from broll.lib.comfyui_lifecycle import ComfyUnavailableError
from pipeline import broll as broll_pipeline


def _make_clip(path: Path, seconds: float) -> None:
    """Render a real N-second test video with ffmpeg (color source)."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c=blue:s=320x240:d={seconds}:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _probe(path: Path) -> float:
    dur = broll_pipeline._probe_duration(path)
    assert dur is not None
    return dur


def test_trim_clamps_over_long_source(tmp_path: Path) -> None:
    clip = tmp_path / "long.mp4"
    _make_clip(clip, 6.0)
    assert _probe(clip) > 5.0

    changed = broll_pipeline._trim_to_duration(clip, 2.0)
    assert changed is True
    assert _probe(clip) == pytest.approx(2.0, abs=0.2)


def test_trim_loop_pads_short_source(tmp_path: Path) -> None:
    clip = tmp_path / "short.mp4"
    _make_clip(clip, 1.0)

    changed = broll_pipeline._trim_to_duration(clip, 4.0)
    assert changed is True
    assert _probe(clip) == pytest.approx(4.0, abs=0.2)


def test_trim_noop_when_already_right_length(tmp_path: Path) -> None:
    clip = tmp_path / "ok.mp4"
    _make_clip(clip, 3.0)
    assert broll_pipeline._trim_to_duration(clip, 3.0) is False


def test_trim_skips_unreadable_file(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.mp4"
    bogus.write_bytes(b"not a video")
    # Must not raise — unreadable inputs are left untouched.
    assert broll_pipeline._trim_to_duration(bogus, 2.0) is False


def test_ensure_up_fast_path_when_alive(monkeypatch) -> None:
    monkeypatch.setattr(comfyui_lifecycle, "is_alive", lambda url, **k: True)
    called = {"restart": False}
    monkeypatch.setattr(comfyui_lifecycle, "_restart",
                        lambda url: called.__setitem__("restart", True) or True)
    comfyui_lifecycle.ensure_up("http://localhost:8188")
    assert called["restart"] is False


def test_ensure_up_raises_when_down_and_no_restart(monkeypatch) -> None:
    monkeypatch.setattr(comfyui_lifecycle, "is_alive", lambda url, **k: False)
    monkeypatch.setattr(comfyui_lifecycle, "_restart", lambda url: False)
    with pytest.raises(ComfyUnavailableError):
        comfyui_lifecycle.ensure_up("http://localhost:8188", attempts=2, wait_s=0.01)


def test_ensure_up_recovers_after_restart(monkeypatch) -> None:
    states = iter([False, True])  # down, then up after restart

    def fake_alive(url, **k):
        try:
            return next(states)
        except StopIteration:
            return True

    monkeypatch.setattr(comfyui_lifecycle, "is_alive", fake_alive)
    monkeypatch.setattr(comfyui_lifecycle, "_restart", lambda url: True)
    comfyui_lifecycle.ensure_up("http://localhost:8188", attempts=2,
                                wait_s=0.01, poll_timeout_s=1.0)

"""media_fetch cut + ingest clip-materialization tests (no network)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from orchestration.context import StageContext
from orchestration.stages import ingest
from pipeline import media_fetch

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
_needs_ffmpeg = pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


def _make_video(path: Path, seconds: int = 6) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"testsrc2=size=320x240:rate=15:duration={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _ctx(tmp_path, inputs, hooks=None):
    manifest = {"episode_id": "ep", "inputs": inputs}
    return StageContext(
        repo_root=tmp_path, ep_dir=tmp_path / "episodes" / "ep", manifest=manifest,
        bible={}, brain_name="halt", hooks=hooks or {},
    )


# ── media_fetch.cut ──────────────────────────────────────────────────────────

@_needs_ffmpeg
def test_cut_trims_the_requested_range(tmp_path):
    src = _make_video(tmp_path / "src.mp4", seconds=6)
    out = media_fetch.cut(src, 2, 5, tmp_path / "clip.mp4")
    assert out.exists()
    assert 2.5 <= _duration(out) <= 3.5  # ~3s


def test_cut_rejects_non_positive_range(tmp_path):
    with pytest.raises(ValueError, match="greater than start"):
        media_fetch.cut(tmp_path / "x.mp4", 5, 5, tmp_path / "o.mp4")


def test_parse_clip():
    assert media_fetch._parse_clip("12-18") == (12.0, 18.0)
    assert media_fetch._parse_clip(None) is None


# ── ingest materialization ───────────────────────────────────────────────────

@_needs_ffmpeg
def test_ingest_trims_local_clip_into_media_pool(tmp_path):
    src = _make_video(tmp_path / "vid.mp4", seconds=6)
    inputs = [{"id": "hook1", "type": "video", "path": str(src), "use": "hook", "clip": [1, 4]}]
    ctx = _ctx(tmp_path, inputs)

    ingest.execute(ctx)

    pool = ctx.manifest["media_pool"]
    assert len(pool) == 1 and pool[0]["id"] == "hook1" and pool[0]["use"] == "hook"
    trimmed = Path(pool[0]["path"])
    assert trimmed.exists() and 2.5 <= _duration(trimmed) <= 3.5


def test_ingest_downloads_url_via_hook(tmp_path):
    calls = []

    def fake_materialize(item, ctx):
        calls.append((item["id"], tuple(item.get("clip") or ())))
        return f"episodes/ep/media/{item['id']}.mp4"

    # same URL, two parts → hook + broll (the user's part-1/part-2 case)
    inputs = [
        {"id": "hook1", "type": "video", "url": "https://youtu.be/X", "use": "hook", "clip": [12, 18]},
        {"id": "brollA", "type": "video", "url": "https://youtu.be/X", "use": "broll", "clip": [45, 52]},
    ]
    ctx = _ctx(tmp_path, inputs, hooks={"materialize_media": fake_materialize})

    ingest.execute(ctx)

    pool = {m["id"]: m for m in ctx.manifest["media_pool"]}
    assert pool["hook1"]["use"] == "hook" and pool["brollA"]["use"] == "broll"
    assert calls == [("hook1", (12, 18)), ("brollA", (45, 52))]


def test_ingest_passthrough_local_without_clip(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "local.mp4").write_bytes(b"x")
    inputs = [{"id": "m1", "type": "video", "path": "media/local.mp4", "use": "broll"}]
    ctx = _ctx(tmp_path, inputs)
    ingest.execute(ctx)
    # local, no clip → resolved to its on-disk path (repo-relative here)
    assert ctx.manifest["media_pool"][0]["path"] == str(tmp_path / "media" / "local.mp4")

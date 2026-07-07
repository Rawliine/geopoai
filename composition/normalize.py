"""Normalize rendered clips to a uniform profile before the compose concat.

Clips come from different renderers (mapbox, manim, broll) at different sizes,
frame rates, and timebases. `transitions._concat_demuxer` needs them uniform, so
this pass scales+pads each clip to the target profile (contain-fit, black bars),
sets a constant frame rate, and normalizes SAR / pixel format / timebase. Audio
is dropped — composition supplies the final audio (VO + SFX) at mux time.

This is the step that was done by hand for the first episode (the `normalized/`
directory + `compose_norm.json`); wiring it makes the compose stage run unattended.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], label: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = res.stderr[-1500:] if res.stderr else ""
        raise RuntimeError(f"{label} failed:\n{tail}")


def normalize_clip(src: Path, dst: Path, width: int, height: int, fps: int) -> Path:
    """Scale+pad *src* to WxH (contain), constant *fps*, uniform SAR/pixfmt/timebase."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )
    # Note: do NOT force -video_track_timescale here. The transitions pass
    # (xfade) re-encodes intermediates at libx264's default 30fps timebase; a
    # forced 90000 timescale mismatches them and xfade fails to configure.
    _run(
        ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-r", str(fps),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
         "-movflags", "+faststart", str(dst)],
        "normalize_clip",
    )
    return dst


def normalize_spec(
    spec: dict[str, Any],
    *,
    profile: dict[str, Any],
    out_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Normalize every clip in *spec* to *profile* and return a spec that points
    at the normalized files (paths absolute). Offsets/overlays are preserved."""
    w, h, fps = int(profile["width"]), int(profile["height"]), int(profile["fps"])
    norm = dict(spec)
    norm_clips: list[dict[str, Any]] = []
    for clip in spec.get("clips", []):
        src = Path(clip["path"])
        if not src.is_absolute():
            src = repo_root / clip["path"]
        dst = out_dir / f"{clip['clip_id']}.mp4"
        normalize_clip(src, dst, w, h, fps)
        nc = dict(clip)
        nc["path"] = str(dst)
        norm_clips.append(nc)
    norm["clips"] = norm_clips
    return norm

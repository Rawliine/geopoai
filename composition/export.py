"""Per-platform export profiles — W17 implements."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def supports_nvenc() -> bool:
    """Return True if ffmpeg reports h264_nvenc support (mirrors map_renderer/runner.py)."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "h264_nvenc" in result.stdout


def profiles(tokens: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return export profile definitions derived from design tokens."""
    _ = tokens
    codec = "h264_nvenc" if supports_nvenc() else "libx264"
    return {
        "yt_long": {
            "width": 1920,
            "height": 1080,
            "format": "horizontal",
            "fps": 30,
            "video_codec": codec,
            "audio_codec": "aac",
            "audio_bitrate": "192k",
        },
        "shorts": {
            "width": 1080,
            "height": 1920,
            "format": "vertical",
            "fps": 30,
            "video_codec": codec,
            "audio_codec": "aac",
            "audio_bitrate": "192k",
        },
    }


def _probe_video_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def _episode_has_vertical(clip_paths: list[Path]) -> bool:
    for path in clip_paths:
        width, height = _probe_video_size(path)
        if height > width:
            return True
    return False


def encode_profile(
    src: Path,
    dst: Path,
    profile: dict[str, Any],
    *,
    clip_paths: list[Path],
    repo_root: Path,
) -> None:
    """Encode the graded episode master to a platform profile."""
    _ = repo_root
    if profile["format"] == "vertical" and not _episode_has_vertical(clip_paths):
        raise ValueError(
            "shorts profile requires at least one vertical source clip; "
            "horizontal-only episodes cannot auto-crop in W17"
        )

    width = profile["width"]
    height = profile["height"]
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )

    codec = profile["video_codec"]
    codecs_to_try = [codec]
    if codec == "h264_nvenc":
        codecs_to_try.append("libx264")

    last_error = ""
    for attempt_codec in codecs_to_try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-r",
            str(profile["fps"]),
            "-c:v",
            attempt_codec,
        ]
        if attempt_codec == "h264_nvenc":
            cmd.extend(
                [
                    "-preset",
                    "p7",
                    "-tune",
                    "hq",
                    "-rc",
                    "constqp",
                    "-qp",
                    "18",
                ]
            )
        else:
            cmd.extend(["-crf", "18", "-preset", "slow"])
        cmd.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                profile["audio_codec"],
                "-b:a",
                profile["audio_bitrate"],
                "-movflags",
                "+faststart",
                str(dst),
            ]
        )

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return
        last_error = result.stderr[-4000:] if result.stderr else ""

    raise RuntimeError(f"export encode failed:\n{last_error}")

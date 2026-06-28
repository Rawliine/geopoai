"""W26.T4 — composite reserved-region media boxes onto the assembled timeline.

Screen-anchored media (a top-half video box, a lower-third, …) is overlaid here
in post — never decoded in the headless browser. Each overlay is contain-fit
(letterboxed, no stretch), framed with a token-styled border, and gated to its
[start, end] episode-time window. The reserved-region sidecar emitted by the map
renderer ({clip}.regions.json) is the cross-check that placement matches the band
the map kept clear; this pass consumes the explicit specs from the compose spec.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_DEFAULT_BORDER_W = 6


def _resolve(repo_root: Path, path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (repo_root / path).resolve()


def _hex_to_ff(color: str) -> str:
    """'#f1c40f' → '0xf1c40f' (ffmpeg color syntax)."""
    return "0x" + str(color).lstrip("#")


def resolve_region_rect(overlay: dict[str, Any], frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """Resolve an overlay's region/rect to (x, y, w, h) px at the frame size.

    Mirrors media.js `_regionToBand`: explicit `rect` wins; else a named region.
    """
    rect = overlay.get("rect")
    if rect:
        x, y, w, h = rect
        return int(round(x)), int(round(y)), int(round(w)), int(round(h))
    region = str(overlay.get("region", "top"))
    if region == "bottom":
        return 0, frame_h // 2, frame_w, frame_h - frame_h // 2
    if region == "lower-third":
        top = (2 * frame_h) // 3
        return 0, top, frame_w, frame_h - top
    # default + 'top'
    return 0, 0, frame_w, frame_h // 2


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def apply_media_overlays(
    assembled: Path,
    overlays: list[dict[str, Any]],
    workdir: Path,
    *,
    tokens: dict[str, Any],
    repo_root: Path,
    frame_size: tuple[int, int],
) -> Path:
    """Overlay each media box onto *assembled*; return the new clip (or *assembled*)."""
    if not overlays:
        return assembled

    frame_w, frame_h = frame_size
    roles = tokens.get("palette", {}).get("roles", {})
    border_color = _hex_to_ff(roles.get("highlight", {}).get("core", "#f1c40f"))

    inputs: list[str] = ["-i", str(assembled)]
    filters: list[str] = []
    last = "0:v"

    for idx, overlay in enumerate(overlays, start=1):
        src = _resolve(repo_root, overlay["src"])
        if not src.exists():
            raise FileNotFoundError(f"media_overlay src not found: {src}")
        if _is_image(src):
            inputs += ["-loop", "1", "-i", str(src)]
        else:
            inputs += ["-i", str(src)]

        x, y, w, h = resolve_region_rect(overlay, frame_w, frame_h)
        start = float(overlay["start"])
        end = float(overlay["end"])
        border = "" if overlay.get("border") is False else (
            f",drawbox=x=0:y=0:w={w}:h={h}:color={border_color}:t={_DEFAULT_BORDER_W}"
        )

        box = f"m{idx}"
        out = f"v{idx}"
        # contain-fit into the box (letterbox), then optional border.
        filters.append(
            f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1{border}[{box}]"
        )
        filters.append(
            f"[{last}][{box}]overlay={x}:{y}:enable='between(t,{start},{end})'[{out}]"
        )
        last = out

    out_path = workdir / "overlaid.mp4"
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{last}]",
        "-an",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    log.info("ffmpeg [media_overlay]: %d overlay(s)", len(overlays))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stderr[-4000:] if result.stderr else ""
        raise RuntimeError(f"ffmpeg failed during media_overlay:\n{tail}")
    return out_path

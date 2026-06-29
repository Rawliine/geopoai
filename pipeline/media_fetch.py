#!/usr/bin/env python3
"""Fetch a video from a link and optionally cut a [start, end] part of it.

Download (YouTube / TikTok / IG / X / news embeds / file://) reuses
`broll.sources.reference.fetch_url` (yt-dlp + fallbacks + caching). This module
adds exact-range trimming and a small CLI, and is what the orchestration `ingest`
stage calls to materialize `inputs[]` that carry a `clip`.

CLI:
  python pipeline/media_fetch.py <url> [out.mp4] [--clip START-END] [--force]
    - no out, no --clip : download to cache, print the path
    - out               : write the (whole, or --clip part of the) video to out
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)


def fetch(url: str, *, force_refresh: bool = False) -> Path:
    """Download *url* (or resolve a local/file:// path) and return the local mp4."""
    from broll.sources.reference import fetch_url

    return fetch_url(url, force_refresh=force_refresh)


def cut(src: str | Path, start: float, end: float, out: str | Path) -> Path:
    """Trim ``[start, end]`` seconds of *src* into *out* (re-encoded). Returns *out*."""
    src, out = Path(src), Path(out)
    start, end = float(start), float(end)
    if end <= start:
        raise ValueError(f"clip end ({end}) must be greater than start ({start})")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(src), "-t", str(end - start),
        "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out.exists():
        tail = res.stderr[-1500:] if res.stderr else ""
        raise RuntimeError(f"ffmpeg clip [{start},{end}] failed:\n{tail}")
    return out


def fetch_clip(
    url: str,
    out: str | Path,
    *,
    clip: tuple[float, float] | list[float] | None = None,
    force_refresh: bool = False,
) -> Path:
    """Download *url*; write the whole video (or its ``clip`` part) to *out*."""
    src = fetch(url, force_refresh=force_refresh)
    out = Path(out)
    if clip:
        return cut(src, clip[0], clip[1], out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    return out


def _parse_clip(spec: str | None) -> tuple[float, float] | None:
    if not spec:
        return None
    if "-" not in spec:
        raise SystemExit("--clip must be START-END seconds, e.g. 12-18")
    a, b = spec.split("-", 1)
    return (float(a), float(b))


def _cli(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Download a video from a link; optionally cut a part.")
    p.add_argument("url", help="YouTube/TikTok/IG/X/news/file:// link.")
    p.add_argument("out", nargs="?", help="Output mp4. Omit to just download to cache + print path.")
    p.add_argument("--clip", help="Keep only START-END seconds, e.g. 12-18 (requires out).")
    p.add_argument("--force", action="store_true", help="Re-download even if cached.")
    args = p.parse_args(argv)

    clip = _parse_clip(args.clip)
    if clip and not args.out:
        raise SystemExit("--clip needs an output path: media_fetch.py <url> <out.mp4> --clip a-b")

    if args.out:
        out = fetch_clip(args.url, args.out, clip=clip, force_refresh=args.force)
    else:
        out = fetch(args.url, force_refresh=args.force)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

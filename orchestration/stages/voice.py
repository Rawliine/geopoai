"""voice (mechanical placeholder) — verify episodes/<id>/vo.wav is present.

VO is supplied externally for now (S2-pro TTS later). This stage just checks the
file exists and, when ffprobe is available, logs its duration against the script
reading estimate (informational — does not block).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)


def _probe_duration(path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def execute(ctx: StageContext) -> None:
    vo = ctx.ep_dir / "vo.wav"
    if not vo.exists():
        raise FileNotFoundError(
            f"voice stage: {vo} not found — supply the VO wav before running voice."
        )
    dur = _probe_duration(vo)
    if dur is not None:
        wps = ctx.bible.get("thresholds", {}).get("reading_words_per_s", 2.6) or 2.6
        words = sum(
            len(re.findall(r"\b\w+\b", b.get("vo_text", "")))
            for b in ctx.manifest.get("script", {}).get("beats", [])
        )
        est = words / wps if words else 0.0
        log.info("voice: vo.wav %.1fs (script estimate %.1fs)", dur, est)


STAGE = Stage(name="voice", is_brain=False, execute=execute)

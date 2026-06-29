"""voice (mechanical) — produce episodes/<id>/vo.wav.

Two paths, in order:
  1. If vo.wav already exists, verify it (externally supplied — e.g. recorded VO).
  2. Otherwise synthesize it from the script via S2-Pro (fish-speech /v1/tts),
     using the server at GEOPOAI_TTS_URL (the `s2pro` Verda workload).

The synth call is behind ctx.hooks['synthesize_vo'] so tests stub it. When ffprobe
is available the duration is logged against the script reading estimate.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)


def _strip_emphasis(text: str) -> str:
    # VO text carries **emphasis** markup; drop the markers, keep the words.
    return re.sub(r"\*\*", "", text)


def script_to_vo_text(manifest: dict) -> str:
    """Flatten the script beats into one VO transcript (emphasis markup removed)."""
    beats = manifest.get("script", {}).get("beats", [])
    parts = [_strip_emphasis(b.get("vo_text", "")).strip() for b in beats]
    return " ".join(p for p in parts if p)


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


def _default_synth(text: str, out_wav, ctx: StageContext) -> None:
    """Synthesize via the S2-Pro server configured by GEOPOAI_TTS_URL."""
    url = os.environ.get("GEOPOAI_TTS_URL")
    if not url:
        raise RuntimeError(
            "voice: no vo.wav and GEOPOAI_TTS_URL is unset — bring up the s2pro "
            "workload (infra/workloads/s2pro.tfvars) or supply episodes/"
            f"{ctx.manifest['episode_id']}/vo.wav"
        )
    from pipeline.tts import synthesize

    synthesize(
        text, out_wav,
        url=url,
        api_key=os.environ.get("GEOPOAI_TTS_API_KEY"),
        reference_audio=os.environ.get("GEOPOAI_TTS_REFERENCE"),
        reference_text=os.environ.get("GEOPOAI_TTS_REFERENCE_TEXT"),
    )


def execute(ctx: StageContext) -> None:
    vo = ctx.ep_dir / "vo.wav"

    if not vo.exists():
        text = script_to_vo_text(ctx.manifest)
        if not text:
            raise ValueError(
                "voice: no vo.wav supplied and the script has no VO text to synthesize"
            )
        synth = ctx.hooks.get("synthesize_vo", _default_synth)
        log.info("voice: synthesizing vo.wav from script (%d chars)", len(text))
        synth(text, vo, ctx)
        if not vo.exists():
            raise RuntimeError("voice: synthesis did not produce vo.wav")

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

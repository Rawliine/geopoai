"""voice (mechanical) — produce episodes/<id>/vo.wav.

Two paths, in order:
  1. If vo.wav already exists, verify it (externally supplied — e.g. recorded VO).
  2. Otherwise synthesize it from the script via S2-Pro (fish-speech /v1/tts),
     using the server at GEOPOAI_TTS_URL (the `s2pro` Verda workload).

The synth call is behind ctx.hooks['synthesize_vo'] so tests stub it. When ffprobe
is available the duration is logged against the script reading estimate.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from orchestration import bible as bible_mod
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


def _resolve_reference(ctx: StageContext) -> tuple[str | None, str | None]:
    """Resolve the pinned reference clip + transcript.

    Bible `voice` block is the source of truth (one consistent cloned voice per
    show); env vars are the fallback/override. A configured-but-missing clip logs
    a warning and falls back to unreferenced synth so the run still completes.
    """
    voice_cfg = bible_mod.voice(ctx.bible)
    ref_audio = voice_cfg.get("reference_audio") or os.environ.get("GEOPOAI_TTS_REFERENCE")
    ref_text = voice_cfg.get("reference_text") or os.environ.get("GEOPOAI_TTS_REFERENCE_TEXT")
    if ref_audio:
        p = Path(ref_audio)
        if not p.is_absolute():
            p = ctx.repo_root / ref_audio
        if p.exists():
            return str(p), ref_text
        log.warning(
            "voice: reference_audio %s not found — synthesizing without a "
            "reference; the cloned voice may vary. Register the clip (assets/"
            "voice/) and set config bible `voice.reference_audio`.", p,
        )
        return None, None
    log.warning(
        "voice: no reference clip pinned (bible `voice.reference_audio` unset) — "
        "S2-Pro will use a default voice that can vary between runs."
    )
    return None, None


def _default_synth(text: str, out_wav, ctx: StageContext) -> None:
    """Synthesize via the S2-Pro server configured by GEOPOAI_TTS_URL.

    Synthesizes in sentence-group chunks — all against the SAME pinned reference,
    so the voice stays consistent — then concatenates. Chunking is required because
    S2-Pro caps a single generation (~1024 tokens ≈ 47s); a long script synthesized
    in one call gets truncated. (The original episode's per-beat calls were the
    right shape but used NO reference, so each chunk drifted to a new voice.)
    """
    url = os.environ.get("GEOPOAI_TTS_URL")
    if not url:
        raise RuntimeError(
            "voice: no vo.wav and GEOPOAI_TTS_URL is unset — bring up the s2pro "
            "workload (infra/workloads/s2pro.tfvars) or supply episodes/"
            f"{ctx.manifest['episode_id']}/vo.wav"
        )
    from pipeline.tts import synthesize

    ref_audio, ref_text = _resolve_reference(ctx)
    api_key = os.environ.get("GEOPOAI_TTS_API_KEY")
    chunks = _sentence_chunks(text)
    out_wav = Path(out_wav)

    if len(chunks) <= 1:
        synthesize(text, out_wav, url=url, api_key=api_key,
                   reference_audio=ref_audio, reference_text=ref_text)
        return

    import tempfile

    with tempfile.TemporaryDirectory(prefix="geopoai-vo-") as td:
        tmp = Path(td)
        parts = []
        for i, chunk in enumerate(chunks):
            p = tmp / f"chunk_{i:03d}.wav"
            synthesize(chunk, p, url=url, api_key=api_key,
                       reference_audio=ref_audio, reference_text=ref_text)
            parts.append(p)
        log.info("voice: synthesized %d chunks against the pinned reference", len(parts))
        listfile = tmp / "list.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
            check=True, capture_output=True,
        )


def _sentence_chunks(text: str, max_chars: int = 320) -> list[str]:
    """Split VO text into sentence-groups under *max_chars* (keeps each synth
    call inside S2-Pro's per-generation length so nothing truncates)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + 1 + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def _default_align(vo_wav, script_text: str) -> list[dict]:
    """Forced-align the VO to word timestamps via tools/align_vo (stable-ts)."""
    from tools.align_vo import align_vo

    return align_vo(Path(vo_wav), script_text or None)


def _build_timing(ctx: StageContext, vo: "Path") -> None:
    """Align the VO and store the per-beat/per-sentence timing map on the manifest.

    This makes the measured voice the master clock: storyboard/scenes derive clip
    durations from these spans (see orchestration.timing). Alignment is behind
    ctx.hooks['align_vo'] so tests stub the heavy whisper call.
    """
    from orchestration import timing as timing_mod

    beats = ctx.manifest.get("script", {}).get("beats", [])
    if not beats:
        return
    script_text = script_to_vo_text(ctx.manifest)
    align = ctx.hooks.get("align_vo", _default_align)
    try:
        words = align(vo, script_text)
    except Exception as exc:  # noqa: BLE001 — alignment is best-effort
        log.warning("voice: alignment failed (%s) — no timing map; clip durations "
                    "will fall back to storyboard values", exc)
        return
    if not words:
        log.warning("voice: alignment produced no words — skipping timing map")
        return
    (ctx.ep_dir / "vo.words.json").write_text(
        json.dumps(words, indent=2) + "\n", encoding="utf-8"
    )
    ctx.manifest["timing"] = timing_mod.build_timing(beats, words)
    log.info(
        "voice: timing map for %d beats (vo_duration %.1fs)",
        len(beats), ctx.manifest["timing"]["vo_duration"],
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

    # Master clock: align the VO and build the timing map the storyboard/scenes
    # derive clip durations from.
    _build_timing(ctx, vo)


STAGE = Stage(name="voice", is_brain=False, execute=execute)

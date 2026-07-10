"""VO timing map — make the measured voiceover the master clock.

`build_timing(beats, words)` turns forced-alignment word timestamps
(`vo.words.json`) into per-beat and per-sentence spans. Because alignment is
forced against the exact script, the aligned word stream follows beat/sentence
order, so we walk it by cumulative word count to find contiguous, non-overlapping
spans that tile the whole audio.

`derive_clip_durations(entries, timing)` then splits each beat's measured span
across the storyboard clips that render it — so every clip duration comes from
real audio, not a human guess. This eliminates drift and makes the final-mux
`-shortest` truncation structurally impossible (durations sum to vo_duration).
"""

from __future__ import annotations

import re
from typing import Any

_WORD_RE = re.compile(r"\b\w+\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _strip_emphasis(text: str) -> str:
    return text.replace("**", "")


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip())]
    return [s for s in parts if s]


def _span(words: list[dict[str, Any]], lo: int, hi: int) -> tuple[float, float]:
    """[start, end] of words[lo:hi], guarding empty/overrun ranges."""
    if not words:
        return (0.0, 0.0)
    lo = max(0, min(lo, len(words) - 1))
    hi = max(lo + 1, min(hi, len(words)))
    return (float(words[lo]["start"]), float(words[hi - 1]["end"]))


def build_timing(
    beats: list[dict[str, Any]],
    words: list[dict[str, Any]],
    audio_duration: float | None = None,
) -> dict[str, Any]:
    """Build the timing map from script *beats* and aligned *words*.

    Returns ``{vo_duration, beats: {beat_id: {start, end, duration,
    sentences: [{text, start, end, duration}]}}}``. Spans are contiguous and
    tile [0, vo_duration].

    *audio_duration* (the measured length of the VO file, e.g. ffprobe) is the
    source of truth for ``vo_duration`` when given — the last aligned word ends
    before the audio does (natural decay / TTS tail), so using ``words[-1].end``
    drops that trailing span. When omitted we fall back to the last word end.
    """
    last_word_end = float(words[-1]["end"]) if words else 0.0
    # The audio file is never shorter than its last spoken word; only trust a
    # measured length that extends past it (trailing decay), never one that would
    # shrink the span below the words (bad probe / inconsistent stub).
    vo_duration = max(last_word_end, float(audio_duration)) if audio_duration else last_word_end
    total_words = sum(_word_count(_strip_emphasis(b.get("vo_text", ""))) for b in beats)
    # Scale factor maps script word counts onto the aligned stream length so
    # tokenization differences (punctuation, contractions) don't drift the tail.
    scale = (len(words) / total_words) if total_words else 1.0

    out_beats: dict[str, Any] = {}
    cursor = 0
    for i, beat in enumerate(beats):
        is_last_beat = i == len(beats) - 1
        text = _strip_emphasis(beat.get("vo_text", ""))
        bwords = _word_count(text)
        # Last beat consumes the remainder so spans tile the whole audio.
        if is_last_beat:
            end_idx = len(words)
        else:
            end_idx = min(len(words), cursor + max(1, round(bwords * scale)))
        start_idx = min(cursor, max(0, end_idx - 1))
        b_start, b_end = _span(words, start_idx, end_idx)
        # Extend the final beat to the true audio end (trailing decay past the
        # last aligned word) so the map tiles [0, vo_duration] exactly.
        if is_last_beat:
            b_end = max(b_end, vo_duration)

        sentences = []
        s_cursor = start_idx
        sent_texts = _split_sentences(text) or [text]
        for j, sent in enumerate(sent_texts):
            is_last_sentence = j == len(sent_texts) - 1
            swords = _word_count(sent)
            if is_last_sentence:
                s_end = end_idx
            else:
                s_end = min(end_idx, s_cursor + max(1, round(swords * scale)))
            s_lo = min(s_cursor, max(start_idx, s_end - 1))
            ss, se = _span(words, s_lo, s_end)
            if is_last_beat and is_last_sentence:
                se = max(se, vo_duration)
            sentences.append({"text": sent, "start": ss, "end": se,
                              "duration": round(se - ss, 3)})
            s_cursor = s_end

        out_beats[beat.get("beat_id") or f"beat_{i}"] = {
            "start": round(b_start, 3),
            "end": round(b_end, 3),
            "duration": round(b_end - b_start, 3),
            "sentences": sentences,
        }
        cursor = end_idx

    return {"vo_duration": round(vo_duration, 3), "beats": out_beats}


def derive_clip_durations(
    entries: list[dict[str, Any]], timing: dict[str, Any]
) -> dict[str, float]:
    """Tile the VO across the storyboard clips so their durations sum to the full
    audio length — no pause is dropped.

    Each clip gets a global *start* time (its sentence group's first sentence, or
    an even split of the beat span when a beat has fewer sentences than clips).
    The clips then partition ``[0, vo_duration]``: clip 0 runs from 0 (absorbing
    any lead-in), each later clip from its own start, and the last clip to
    ``vo_duration``. So ``sum(durations) == vo_duration`` — the assembled video
    matches the voiceover and the final-mux ``-shortest`` cannot truncate the
    tail. (The old sentence-span sum dropped inter-sentence and inter-beat pauses,
    leaving the video short of the audio.) Clips whose beat has no timing span are
    skipped, as before.
    """
    beats_timing = timing.get("beats", {})
    vo_duration = float(timing.get("vo_duration", 0.0))

    # group entries by beat, preserving storyboard order
    by_beat: dict[str, list[dict]] = {}
    for e in entries:
        by_beat.setdefault(e["beat_id"], []).append(e)

    # per-clip global start time
    starts: dict[str, float] = {}
    for beat_id, clips in by_beat.items():
        bt = beats_timing.get(beat_id)
        if not bt or not clips:
            continue
        sentences = bt.get("sentences", [])
        k = len(clips)
        if len(sentences) >= k and sentences:
            n = len(sentences)
            for i, clip in enumerate(clips):
                lo = (i * n) // k
                starts[clip["clip_id"]] = float(sentences[lo]["start"])
        else:
            b_start = float(bt["start"])
            b_dur = float(bt["duration"])
            for i, clip in enumerate(clips):
                starts[clip["clip_id"]] = round(b_start + i * (b_dur / k), 3)

    # ordered clip ids that have a start, in storyboard order; partition [0, vo]
    ordered = [e["clip_id"] for e in entries if e["clip_id"] in starts]
    durations: dict[str, float] = {}
    for idx, clip_id in enumerate(ordered):
        lo = 0.0 if idx == 0 else starts[clip_id]
        hi = starts[ordered[idx + 1]] if idx + 1 < len(ordered) else vo_duration
        durations[clip_id] = max(0.001, round(hi - lo, 3))
    return durations

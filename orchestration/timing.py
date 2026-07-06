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


def build_timing(beats: list[dict[str, Any]], words: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the timing map from script *beats* and aligned *words*.

    Returns ``{vo_duration, beats: {beat_id: {start, end, duration,
    sentences: [{text, start, end, duration}]}}}``. Spans are contiguous and
    tile [0, vo_duration].
    """
    vo_duration = float(words[-1]["end"]) if words else 0.0
    total_words = sum(_word_count(_strip_emphasis(b.get("vo_text", ""))) for b in beats)
    # Scale factor maps script word counts onto the aligned stream length so
    # tokenization differences (punctuation, contractions) don't drift the tail.
    scale = (len(words) / total_words) if total_words else 1.0

    out_beats: dict[str, Any] = {}
    cursor = 0
    for i, beat in enumerate(beats):
        text = _strip_emphasis(beat.get("vo_text", ""))
        bwords = _word_count(text)
        # Last beat consumes the remainder so spans tile the whole audio.
        if i == len(beats) - 1:
            end_idx = len(words)
        else:
            end_idx = min(len(words), cursor + max(1, round(bwords * scale)))
        start_idx = min(cursor, max(0, end_idx - 1))
        b_start, b_end = _span(words, start_idx, end_idx)

        sentences = []
        s_cursor = start_idx
        sent_texts = _split_sentences(text) or [text]
        for j, sent in enumerate(sent_texts):
            swords = _word_count(sent)
            if j == len(sent_texts) - 1:
                s_end = end_idx
            else:
                s_end = min(end_idx, s_cursor + max(1, round(swords * scale)))
            s_lo = min(s_cursor, max(start_idx, s_end - 1))
            ss, se = _span(words, s_lo, s_end)
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
    """Split each beat's measured span across the clips that render it.

    Clips within a beat keep storyboard order. When a beat has at least as many
    sentences as clips, consecutive sentences are grouped per clip (so each clip
    owns a real span of speech); otherwise the beat duration is split evenly.
    Returns ``{clip_id: duration_s}`` for every entry whose beat is in *timing*.
    """
    beats_timing = timing.get("beats", {})
    # group entries by beat, preserving order
    by_beat: dict[str, list[dict]] = {}
    for e in entries:
        by_beat.setdefault(e["beat_id"], []).append(e)

    durations: dict[str, float] = {}
    for beat_id, clips in by_beat.items():
        bt = beats_timing.get(beat_id)
        if not bt:
            continue
        sentences = bt.get("sentences", [])
        k = len(clips)
        if k == 0:
            continue
        if len(sentences) >= k and sentences:
            # assign consecutive sentence groups to clips
            n = len(sentences)
            for i, clip in enumerate(clips):
                lo = (i * n) // k
                hi = ((i + 1) * n) // k if i < k - 1 else n
                grp = sentences[lo:hi] or [sentences[min(lo, n - 1)]]
                durations[clip["clip_id"]] = round(
                    sum(float(s["duration"]) for s in grp), 3
                )
        else:
            share = round(float(bt["duration"]) / k, 3)
            for clip in clips:
                durations[clip["clip_id"]] = share
    return durations

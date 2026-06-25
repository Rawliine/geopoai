"""Caption burn-in — word chunks (W15); ASS/placement in later tasks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GAP_MERGE_S = 0.12

_NUMBER_UNIT_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)(%|km|mi|miles|mph|km/h|m|ft|tons?|bn|million|billion)?$",
    re.IGNORECASE,
)
_PUNCT_BREAK_RE = re.compile(r"[.!?;:]$")
_EMPHASIS_RE = re.compile(r"\*\*([^*]+)\*\*")


@dataclass(frozen=True)
class Word:
    word: str
    start: float
    end: float
    confidence: float
    emphasis: bool = False


@dataclass(frozen=True)
class Chunk:
    words: tuple[str, ...]
    emphasis: tuple[bool, ...]
    start: float
    end: float

    @property
    def text(self) -> str:
        return " ".join(self.words)


def load_words(path: Path, script_text: str | None = None) -> list[Word]:
    """Load alignment JSON and attach emphasis flags from optional script."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    emphasized = emphasis_words_from_script(script_text) if script_text else set()
    words: list[Word] = []
    for item in raw:
        token = _clean_token(str(item["word"]))
        if not token:
            continue
        key = re.sub(r"[^\w]", "", token).lower()
        words.append(
            Word(
                word=token,
                start=float(item["start"]),
                end=float(item["end"]),
                confidence=float(item.get("confidence", 1.0)),
                emphasis=key in emphasized,
            )
        )
    return words


def emphasis_words_from_script(script_text: str) -> set[str]:
    """Return lowercase word keys that were wrapped in ``**`` in the script."""
    found: set[str] = set()
    for match in _EMPHASIS_RE.finditer(script_text):
        for token in match.group(1).split():
            key = re.sub(r"[^\w]", "", token).lower()
            if key:
                found.add(key)
    return found


def _clean_token(token: str) -> str:
    return token.strip().strip("*").strip()


def _is_number_unit_pair(left: str, right: str) -> bool:
    return bool(_NUMBER_UNIT_RE.match(left)) and bool(
        _NUMBER_UNIT_RE.match(right) and re.search(r"[a-z%]", right, re.I)
    )


def chunk_words(
    words: list[Word],
    tokens: dict[str, Any],
    *,
    script_text: str | None = None,
) -> list[Chunk]:
    """Group aligned words into 1–3 word caption chunks."""
    if script_text:
        emphasized = emphasis_words_from_script(script_text)
        words = [
            Word(
                w.word,
                w.start,
                w.end,
                w.confidence,
                emphasis=(re.sub(r"[^\w]", "", w.word).lower() in emphasized),
            )
            for w in words
        ]

    min_s = float(tokens["timing"]["callout_min_s"])
    chunks: list[Chunk] = []
    bucket: list[Word] = []

    def flush() -> None:
        nonlocal bucket
        if not bucket:
            return
        start = bucket[0].start
        end = max(w.end for w in bucket)
        if end - start < min_s:
            end = start + min_s
        chunks.append(
            Chunk(
                words=tuple(w.word for w in bucket),
                emphasis=tuple(w.emphasis for w in bucket),
                start=start,
                end=end,
            )
        )
        bucket = []

    for word in words:
        if bucket and len(bucket) >= 3:
            flush()
        if bucket:
            prev = bucket[-1]
            if _is_number_unit_pair(prev.word, word.word):
                bucket.append(word)
                flush()
                continue
            if _PUNCT_BREAK_RE.search(prev.word):
                flush()
        bucket.append(word)
        if _PUNCT_BREAK_RE.search(word.word):
            flush()

    flush()
    return _merge_short_gaps(chunks, min_s)


def _merge_short_gaps(chunks: list[Chunk], min_s: float) -> list[Chunk]:
    if not chunks:
        return chunks
    merged: list[Chunk] = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        gap = chunk.start - prev.end
        if gap < GAP_MERGE_S and len(prev.words) + len(chunk.words) <= 3:
            merged[-1] = Chunk(
                words=prev.words + chunk.words,
                emphasis=prev.emphasis + chunk.emphasis,
                start=prev.start,
                end=max(prev.end, chunk.end),
            )
        else:
            merged.append(chunk)
    return [
        Chunk(c.words, c.emphasis, c.start, max(c.end, c.start + min_s))
        for c in merged
    ]


def build(
    vo_wav: Path,
    words_json: Path | None,
    layout_jsons: list[Path],
    tokens: dict[str, Any],
    fmt: str,
) -> Path:
    """Build an ASS subtitle file from VO alignment and occupancy layouts."""
    raise NotImplementedError("ASS generation is implemented in W15.T3+")

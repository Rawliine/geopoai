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


def _hex_to_ass_bgr(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"{b:02X}{g:02X}{r:02X}"


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _caption_font_size(tokens: dict[str, Any], fmt: str) -> int:
    return int(tokens["typography"]["scale"][fmt]["caption"])


def _play_res(fmt: str) -> tuple[int, int]:
    return (1080, 1920) if fmt == "vertical" else (1920, 1080)


def _band_center_y(band: tuple[float, float]) -> float:
    return (band[0] + band[1]) / 2.0


def _styled_dialogue(
    chunk: Chunk,
    tokens: dict[str, Any],
    fmt: str,
    band: tuple[float, float],
) -> str:
    width, height = _play_res(fmt)
    cy = _band_center_y(band)
    y = int(cy * height)
    primary = tokens["typography"]["primary"]
    size = _caption_font_size(tokens, fmt)
    text_color = _hex_to_ass_bgr(tokens["palette"]["text"]["primary"])
    highlight = _hex_to_ass_bgr(tokens["palette"]["roles"]["highlight"]["core"])
    back = _hex_to_ass_bgr(tokens["palette"]["background"])

    parts: list[str] = []
    for word, emph in zip(chunk.words, chunk.emphasis, strict=False):
        if emph:
            parts.append(f"{{\\c&H{highlight}&}}{word}{{\\c&H{text_color}&}}")
        else:
            parts.append(word)
    text = " ".join(parts)
    start = _ass_time(chunk.start)
    end = _ass_time(chunk.end)
    return (
        f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{{\\an8\\pos({width // 2},{y})"
        f"\\fn{primary}\\fs{size}\\c&H{text_color}&\\bord2\\3c&H{back}&"
        f"\\shad0\\borderstyle3}}{text}"
    )


def write_ass(
    chunks: list[Chunk],
    tokens: dict[str, Any],
    fmt: str,
    out_path: Path,
    *,
    band: tuple[float, float] | None = None,
) -> Path:
    """Write a brand-minimal ASS transcript strip at the caption band."""
    width, height = _play_res(fmt)
    caption_band = band or tuple(tokens["safe_areas"][fmt]["caption_band"])
    header = [
        "[Script Info]",
        "Title: GeoPoAI captions",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            f"Style: Caption,{tokens['typography']['primary']},{_caption_font_size(tokens, fmt)},"
            f"&H{_hex_to_ass_bgr(tokens['palette']['text']['primary'])}&,"
            f"&HFFFFFF&,&H{_hex_to_ass_bgr(tokens['palette']['background'])}&,"
            f"&HAA{_hex_to_ass_bgr(tokens['palette']['background'])}&,0,0,0,0,100,100,0,0,3,2,0,8,40,40,80,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines = list(header)
    for chunk in chunks:
        lines.append(_styled_dialogue(chunk, tokens, fmt, caption_band))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def build(
    vo_wav: Path,
    words_json: Path | None,
    layout_jsons: list[Path],
    tokens: dict[str, Any],
    fmt: str,
    *,
    script_text: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Build an ASS subtitle file from VO alignment (default caption band)."""
    if words_json is None:
        raise ValueError("words_json is required — run tools/align_vo.py first")
    out_dir = output_dir or vo_wav.parent
    ass_path = out_dir / f"{vo_wav.stem}.ass"
    words = load_words(words_json, script_text)
    chunks = chunk_words(words, tokens, script_text=script_text)
    return write_ass(chunks, tokens, fmt, ass_path)

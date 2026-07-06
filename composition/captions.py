"""Caption burn-in — word chunks, occupancy-aware ASS, policy-driven burn windows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Placement tuning (normalized overlap units).
CALLOUT_WEIGHT = 3.0
HYSTERESIS_RATIO = 2.0
HYSTERESIS_THRESHOLD = 0.02
CAPTION_WIDTH_FRAC = 0.88
CAPTION_HEIGHT_FRAC = 0.06
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
    # Burned-in subtitles use the dedicated `subtitle` size (large, for short-form
    # legibility) — distinct from the manim `caption` role (small chart/timeline
    # labels), so bumping one never balloons the other. Fall back to caption.
    scale = tokens["typography"]["scale"][fmt]
    return int(scale.get("subtitle", scale["caption"]))


def _play_res(fmt: str) -> tuple[int, int]:
    return (1080, 1920) if fmt == "vertical" else (1920, 1080)


def _band_center_y(band: tuple[float, float]) -> float:
    return (band[0] + band[1]) / 2.0


def _mirror_band(band: tuple[float, float]) -> tuple[float, float]:
    lo, hi = band
    return (1.0 - hi, 1.0 - lo)


def _mid_low_band(caption_band: tuple[float, float]) -> tuple[float, float]:
    center = _band_center_y(caption_band)
    height = caption_band[1] - caption_band[0]
    mid = 0.5
    return (mid - height / 2, mid + height / 2)


def _candidate_bands(
    tokens: dict[str, Any], fmt: str
) -> list[tuple[str, tuple[float, float]]]:
    caption_band = tuple(tokens["safe_areas"][fmt]["caption_band"])
    return [
        ("default", caption_band),
        ("upper_third", _mirror_band(caption_band)),
        ("mid_low", _mid_low_band(caption_band)),
    ]


def _caption_rect(
    band: tuple[float, float],
    tokens: dict[str, Any],
    fmt: str,
    *,
    height_frac: float = CAPTION_HEIGHT_FRAC,
) -> tuple[float, float, float, float]:
    cy = _band_center_y(band)
    h = min(height_frac, band[1] - band[0])
    margins = tokens["safe_areas"][fmt]["platform_margins"]
    x = float(margins["left"])
    w = 1.0 - float(margins["left"]) - float(margins["right"])
    return (x, cy - h / 2, w, h)


def _box_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0 = max(ax, bx)
    y0 = max(ay, by)
    x1 = min(ax + aw, bx + bw)
    y1 = min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _kind_weight(kind: str) -> float:
    return CALLOUT_WEIGHT if kind == "callout" else 1.0


def _load_shifted_layout_boxes(
    layout_jsons: list[Path],
    clip_offsets: list[float] | None,
    fmt: str,
) -> list[tuple[float, float, str, tuple[float, float, float, float]]]:
    """Return ``(t_start, t_end, kind, box)`` rows in episode time."""
    offsets = clip_offsets or [0.0] * len(layout_jsons)
    rows: list[tuple[float, float, str, tuple[float, float, float, float]]] = []
    for layout_path, offset in zip(layout_jsons, offsets, strict=False):
        doc = json.loads(layout_path.read_text(encoding="utf-8"))
        if doc.get("format") != fmt:
            continue
        frames = doc.get("frames", [])
        hz = float(doc.get("sample_hz", 1.0))
        dt = 1.0 / hz if hz else 1.0
        for frame in frames:
            t = float(frame["t"]) + offset
            for box in frame.get("boxes", []):
                rect = (float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"]))
                rows.append((t, t + dt, str(box["kind"]), rect))
    return rows


def _margin_rect(tokens: dict[str, Any], fmt: str) -> tuple[float, float, float, float]:
    margins = tokens["safe_areas"][fmt]["platform_margins"]
    left = float(margins["left"])
    right = float(margins["right"])
    top = float(margins["top"])
    bottom = float(margins["bottom"])
    return (left, top, 1.0 - left - right, 1.0 - top - bottom)


def _inside_margins(
    rect: tuple[float, float, float, float],
    margin_rect: tuple[float, float, float, float],
) -> bool:
    mx, my, mw, mh = margin_rect
    x, y, w, h = rect
    return x >= mx and y >= my and (x + w) <= (mx + mw) and (y + h) <= (my + mh)


def _overlap_score(
    chunk: Chunk,
    band: tuple[float, float],
    layout_rows: list[tuple[float, float, str, tuple[float, float, float, float]]],
    tokens: dict[str, Any],
    fmt: str,
) -> float:
    caption_rect = _caption_rect(band, tokens, fmt)
    score = 0.0
    for t0, t1, kind, box in layout_rows:
        if t1 < chunk.start or t0 > chunk.end:
            continue
        score += _box_overlap(caption_rect, box) * _kind_weight(kind)
    return score


def place_chunks(
    chunks: list[Chunk],
    tokens: dict[str, Any],
    fmt: str,
    layout_jsons: list[Path],
    clip_offsets: list[float] | None = None,
) -> dict[int, tuple[str, tuple[float, float]]]:
    """Pick a vertical band per chunk with hysteresis to avoid jitter."""
    candidates = _candidate_bands(tokens, fmt)
    layout_rows = _load_shifted_layout_boxes(layout_jsons, clip_offsets, fmt)
    margin_rect = _margin_rect(tokens, fmt)
    placements: dict[int, tuple[str, tuple[float, float]]] = {}
    current: tuple[str, tuple[float, float]] | None = None
    current_score = 0.0

    for idx, chunk in enumerate(chunks):
        scored: list[tuple[str, tuple[float, float], float]] = []
        for name, band in candidates:
            rect = _caption_rect(band, tokens, fmt)
            if not _inside_margins(rect, margin_rect):
                continue
            scored.append(
                (name, band, _overlap_score(chunk, band, layout_rows, tokens, fmt))
            )
        if not scored:
            name, band = candidates[0]
            placements[idx] = (name, band)
            current = (name, band)
            current_score = 0.0
            continue

        scored.sort(key=lambda row: row[2])
        best_name, best_band, best_score = scored[0]

        if current is not None:
            cur_name, cur_band = current
            cur_score = next((s for n, b, s in scored if n == cur_name and b == cur_band), current_score)
            if (
                cur_score <= HYSTERESIS_THRESHOLD
                or best_score >= cur_score
                or best_score > cur_score / HYSTERESIS_RATIO
            ):
                placements[idx] = (cur_name, cur_band)
                current_score = cur_score
                continue

        placements[idx] = (best_name, best_band)
        current = (best_name, best_band)
        current_score = best_score

    return placements


def _chunk_in_burn_window(
    chunk: Chunk, burn_windows: list[tuple[float, float]] | None
) -> bool:
    if burn_windows is None:
        return True
    for start, end in burn_windows:
        if chunk.end > start and chunk.start < end:
            return True
    return False


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
    # Semi-opaque backing via BorderStyle=3 + BackColour alpha (&HAA______).
    back_alpha = f"&HAA{back}&"

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
    placements: dict[int, tuple[str, tuple[float, float]]] | None = None,
    burn_windows: list[tuple[float, float]] | None = None,
) -> Path:
    """Write a brand-minimal ASS transcript strip."""
    width, height = _play_res(fmt)
    placements = placements or {
        i: ("default", tuple(tokens["safe_areas"][fmt]["caption_band"]))
        for i in range(len(chunks))
    }
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
    for idx, chunk in enumerate(chunks):
        if not _chunk_in_burn_window(chunk, burn_windows):
            continue
        _, band = placements.get(
            idx, ("default", tuple(tokens["safe_areas"][fmt]["caption_band"]))
        )
        lines.append(_styled_dialogue(chunk, tokens, fmt, band))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def write_srt(chunks: list[Chunk], out_path: Path) -> Path:
    """Plain SRT sidecar — full transcript, no styling."""
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(str(idx))
        lines.append(f"{_srt_time(chunk.start)} --> {_srt_time(chunk.end)}")
        lines.append(chunk.text)
        lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _policy_burn_ass(caption_policy: dict[str, Any] | None) -> bool:
    if not caption_policy:
        return True
    return str(caption_policy.get("burn_in", "broll_only")) != "never"


def _policy_sidecar(caption_policy: dict[str, Any] | None) -> bool:
    if not caption_policy:
        return True
    return bool(caption_policy.get("sidecar", True))


def build(
    vo_wav: Path,
    words_json: Path | None,
    layout_jsons: list[Path],
    tokens: dict[str, Any],
    fmt: str,
    *,
    clip_offsets: list[float] | None = None,
    burn_windows: list[tuple[float, float]] | None = None,
    caption_policy: dict[str, Any] | None = None,
    script_text: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Build caption artifacts from VO alignment and occupancy layouts.

    When ``burn_windows`` is provided, ASS dialogue lines are emitted only for
    chunks overlapping a window; SRT (when enabled) always carries the full VO.
    ``burn_windows=None`` burns the full aligned timeline (``burn_in: always``).

    Standalone ffmpeg burn-in::

        ffmpeg -y -i input.mp4 -vf "subtitles=captions.ass" -c:a copy burned.mp4

    Args:
        vo_wav: Episode voice-over waveform (used for default output naming).
        words_json: Forced-alignment output; required for W15 builds.
        layout_jsons: Per-clip ``*.layout.json`` shifted by ``clip_offsets``.
        tokens: Parsed design tokens.
        fmt: ``horizontal`` or ``vertical``.
        clip_offsets: Episode offsets parallel to ``layout_jsons``.
        burn_windows: Optional burn intervals in episode seconds.
        caption_policy: ``{burn_in, sidecar}`` episode policy.
        script_text: Optional beats text for emphasis + chunking hints.
        output_dir: Directory for ``.ass`` / ``.srt`` artifacts.

    Returns:
        Path to ``.ass`` when burn-in is enabled, otherwise ``.srt`` when
        sidecar is requested.
    """
    if words_json is None:
        raise ValueError("words_json is required — run tools/align_vo.py first")

    out_dir = output_dir or vo_wav.parent
    stem = vo_wav.stem
    ass_path = out_dir / f"{stem}.ass"
    srt_path = out_dir / f"{stem}.srt"

    words = load_words(words_json, script_text)
    chunks = chunk_words(words, tokens, script_text=script_text)
    placements = place_chunks(chunks, tokens, fmt, layout_jsons, clip_offsets)

    if _policy_sidecar(caption_policy):
        write_srt(chunks, srt_path)

    if _policy_burn_ass(caption_policy):
        write_ass(
            chunks,
            tokens,
            fmt,
            ass_path,
            placements=placements,
            burn_windows=burn_windows,
        )
        return ass_path

    if _policy_sidecar(caption_policy):
        return srt_path
    raise ValueError("caption_policy disables both burn-in and sidecar output")

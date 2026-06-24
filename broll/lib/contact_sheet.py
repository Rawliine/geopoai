"""Contact sheet generation for checkpoint / --ask flows."""

from __future__ import annotations

import json
import logging
import math
import os
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

from .clip_prefilter import ScoredCandidate

log = logging.getLogger("broll.contact_sheet")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise ImportError("contact_sheet requires Pillow (in requirements.txt)") from exc


def _fetch_image(url: str) -> Image.Image | None:
    if url.startswith("file://"):
        path = Path(url[7:])
        if path.exists():
            return Image.open(path)
        return None
    if url.startswith("/") and Path(url).exists():
        return Image.open(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GeoPoAI-broll/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Image.open(BytesIO(resp.read()))
    except Exception as exc:  # noqa: BLE001
        log.warning("contact_sheet: failed to load %s: %s", url, exc)
        return None


def _placeholder(w: int, h: int, label: str) -> Image.Image:
    img = Image.new("RGB", (w, h), color=(40, 40, 48))
    draw = ImageDraw.Draw(img)
    draw.text((8, h // 2 - 8), label[:40], fill=(200, 200, 200))
    return img


def build_contact_sheet(
    entries: list[dict[str, Any]],
    *,
    thumb_w: int = 320,
    thumb_h: int = 180,
    cols: int = 4,
) -> Image.Image:
    """Build a thumbnail grid PNG from ``entries`` (each needs id, label, thumb_url)."""
    if not entries:
        raise ValueError("entries must not be empty")
    cols = max(1, min(cols, len(entries)))
    rows = math.ceil(len(entries) / cols)
    pad = 8
    label_h = 24
    sheet_w = cols * (thumb_w + pad) + pad
    sheet_h = rows * (thumb_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), color=(24, 24, 28))

    for i, entry in enumerate(entries):
        col = i % cols
        row = i // cols
        x = pad + col * (thumb_w + pad)
        y = pad + row * (thumb_h + label_h + pad)

        thumb = _fetch_image(entry.get("thumb_url") or "")
        if thumb is None:
            thumb = _placeholder(thumb_w, thumb_h, entry.get("id", "?"))
        else:
            thumb = thumb.convert("RGB")
            thumb.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (thumb_w, thumb_h), (32, 32, 36))
            ox = (thumb_w - thumb.width) // 2
            oy = (thumb_h - thumb.height) // 2
            canvas.paste(thumb, (ox, oy))
            thumb = canvas

        sheet.paste(thumb, (x, y))
        draw = ImageDraw.Draw(sheet)
        label = entry.get("label") or entry.get("id") or str(i)
        draw.text((x, y + thumb_h + 2), label[:48], fill=(220, 220, 220))

    return sheet


def write_verifier_checkpoint(
    intent: str,
    candidates: list[ScoredCandidate],
    output_dir: Path,
    *,
    shot_id: str = "checkpoint",
) -> dict[str, str]:
    """Write contact sheet + candidates.json for verifier checkpoint mode."""
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    serializable: list[dict[str, Any]] = []
    for i, sc in enumerate(candidates):
        seg_id = f"cand_{i}"
        ts = sc.result.source_metadata.get("start_seconds")
        label = f"{seg_id}"
        if ts is not None:
            label = f"{seg_id} @ {ts:.1f}s"
        entries.append({
            "id": seg_id,
            "label": label,
            "thumb_url": sc.result.thumbnail_url or sc.result.download_url,
        })
        serializable.append({
            "segment_id": seg_id,
            "index": i,
            "score": sc.score,
            "source": sc.result.source_name,
            "title": sc.result.title,
            "thumbnail_url": sc.result.thumbnail_url,
            "download_url": sc.result.download_url,
            "start_seconds": sc.result.source_metadata.get("start_seconds"),
            "end_seconds": sc.result.source_metadata.get("end_seconds"),
        })

    sheet = build_contact_sheet(entries)
    sheet_path = output_dir / f"{shot_id}_contact_sheet.png"
    sheet.save(sheet_path, format="PNG")

    cand_path = output_dir / f"{shot_id}_candidates.json"
    cand_path.write_text(
        json.dumps({"intent": intent, "shot_id": shot_id, "candidates": serializable}, indent=2),
        encoding="utf-8",
    )
    return {"contact_sheet": str(sheet_path), "candidates_json": str(cand_path)}


def write_reference_checkpoint(
    intent: str,
    segments: list[dict[str, Any]],
    output_dir: Path,
    *,
    shot_id: str,
) -> dict[str, str]:
    """Write contact sheet + candidates.json for reference --ask mode."""
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for seg in segments:
        seg_id = seg["segment_id"]
        ts = seg.get("start_seconds", 0)
        entries.append({
            "id": seg_id,
            "label": f"{seg_id} @ {ts:.1f}s",
            "thumb_url": seg.get("thumb_path") or seg.get("thumb_url") or "",
        })

    sheet = build_contact_sheet(entries)
    sheet_path = output_dir / f"{shot_id}_contact_sheet.png"
    sheet.save(sheet_path, format="PNG")

    cand_path = output_dir / f"{shot_id}_candidates.json"
    cand_path.write_text(
        json.dumps({"intent": intent, "shot_id": shot_id, "segments": segments}, indent=2),
        encoding="utf-8",
    )
    return {"contact_sheet": str(sheet_path), "candidates_json": str(cand_path)}

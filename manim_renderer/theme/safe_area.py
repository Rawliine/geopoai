"""Platform-safe content region, derived from design tokens.

Short-form platforms overlay UI (caption bands, like/share rails) on top of the
video. `config/design_tokens.json` records, per format, a `caption_band`
(normalized y-range, measured from the top) and `platform_margins` (fractions of
each edge). This module turns those into Manim scene-unit geometry so the
renderer can keep every component inside the usable area — above the caption
band and within the margins.

The forbidden caption band is treated as a hard floor: content must sit entirely
ABOVE it (its bottom edge no lower than the band's top edge). All values are
token-derived; nothing here is a hand-tuned constant.
"""

from __future__ import annotations

from functools import lru_cache

from manim_renderer.layouts.base import FRAME_BOUNDS, Rect

# Token fallbacks (mirror config/design_tokens.json) so the renderer still works
# if the tokens file is unreadable — same defensive pattern as theme/palette.py.
_SAFE_FALLBACK: dict[str, dict] = {
    "vertical": {
        "caption_band": [0.78, 0.92],
        "platform_margins": {"top": 0.06, "bottom": 0.10, "left": 0.04, "right": 0.14},
    },
    "horizontal": {
        "caption_band": [0.84, 0.96],
        "platform_margins": {"top": 0.04, "bottom": 0.04, "left": 0.04, "right": 0.04},
    },
}


def _safe_tokens(fmt: str) -> dict:
    try:
        from tools.tokens import load_tokens

        areas = load_tokens()["safe_areas"]
        return areas[fmt]
    except (ImportError, FileNotFoundError, KeyError, TypeError):
        return _SAFE_FALLBACK.get(fmt, _SAFE_FALLBACK["horizontal"])


def caption_band(fmt: str) -> tuple[float, float]:
    """Caption band as a normalized (top, bottom) y-range measured from the
    frame top (0=top, 1=bottom)."""
    band = _safe_tokens(fmt).get("caption_band", _SAFE_FALLBACK[fmt]["caption_band"])
    return float(band[0]), float(band[1])


def platform_margins(fmt: str) -> dict[str, float]:
    """Per-edge margins as fractions of the frame (top/bottom/left/right)."""
    m = _safe_tokens(fmt).get("platform_margins", _SAFE_FALLBACK[fmt]["platform_margins"])
    return {k: float(m[k]) for k in ("top", "bottom", "left", "right")}


@lru_cache(maxsize=4)
def safe_content_rect(fmt: str) -> Rect:
    """Largest rect (Manim units, origin centre, y-up) that excludes the
    platform margins AND sits entirely above the caption band."""
    fw, fh = FRAME_BOUNDS.get(fmt, FRAME_BOUNDS["horizontal"])
    m = platform_margins(fmt)
    band_top_norm, _band_bottom_norm = caption_band(fmt)

    # A token-derived breathing gap so content clears the band edge cleanly
    # (also keeps the boundary strict against float rounding).
    from manim_renderer.theme.spacing import spacing
    clearance = spacing("label_gap", fmt)

    left = -fw / 2.0 + m["left"] * fw
    right = fw / 2.0 - m["right"] * fw
    top = fh / 2.0 - m["top"] * fh
    # Bottom edge: the higher (less negative) of the bottom-margin edge and the
    # caption band's TOP edge (plus the clearance gap) — content never enters
    # the band.
    bottom_margin_edge = -fh / 2.0 + m["bottom"] * fh
    band_top_manim = fh / 2.0 - band_top_norm * fh + clearance
    bottom = max(bottom_margin_edge, band_top_manim)

    return Rect(
        cx=(left + right) / 2.0,
        cy=(bottom + top) / 2.0,
        width=right - left,
        height=top - bottom,
    )


def clamp_center(cx: float, cy: float, w: float, h: float, fmt: str) -> tuple[float, float]:
    """Shift a bbox centre so a w×h box stays inside the safe content rect.
    A box larger than the safe rect on an axis is centred on that axis."""
    safe = safe_content_rect(fmt)
    left = safe.cx - safe.width / 2.0
    right = safe.cx + safe.width / 2.0
    bottom = safe.cy - safe.height / 2.0
    top = safe.cy + safe.height / 2.0
    hw, hh = w / 2.0, h / 2.0

    cx = safe.cx if 2.0 * hw >= safe.width else min(max(cx, left + hw), right - hw)
    cy = safe.cy if 2.0 * hh >= safe.height else min(max(cy, bottom + hh), top - hh)
    return cx, cy


def clamp_rect(rect: Rect, fmt: str) -> Rect:
    """Return `rect` shrunk (if needed) and shifted to fit inside the safe
    content rect — used to keep solved component rects out of the caption band
    and platform margins."""
    safe = safe_content_rect(fmt)
    w = min(rect.width, safe.width)
    h = min(rect.height, safe.height)
    cx, cy = clamp_center(rect.cx, rect.cy, w, h, fmt)
    return Rect(cx=cx, cy=cy, width=w, height=h)

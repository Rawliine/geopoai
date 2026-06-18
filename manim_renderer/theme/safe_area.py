"""Platform-safe content region, derived from design tokens — with policy.

Short-form platforms overlay UI on top of the video. `config/design_tokens.json`
records, per format, a `caption_band` (normalized y-range from the top, where a
burned-in VO transcript sits) and `platform_margins` (per-edge fractions, e.g.
the right inset on 9:16 for the like/share rail).

These are TWO independent concerns and are toggled independently — they protect
against different things:

  * platform_margins — platform UI chrome (matters for the deliverable).
  * caption_band     — burned-in captions (only matters when captions are on).

Geometry lives in the tokens; whether each applies is *policy*. Defaults are
format-derived (vertical Shorts → both on; horizontal long-form → both off), and
a scene may override via ``scene.safe_areas = {platform_margins, caption_band}``.

Cross-lane follow-up (lead-owned, out of W10's allowlist): lift this policy into
``compose.schema.json`` flags + a shared ``safe_area_policy`` passed into each
render, so one authored clip can export under different policies. Until then the
per-scene override is the escape hatch.
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

_NO_MARGINS = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}


def _safe_tokens(fmt: str) -> dict:
    try:
        from tools.tokens import load_tokens

        return load_tokens()["safe_areas"][fmt]
    except (ImportError, FileNotFoundError, KeyError, TypeError):
        return _SAFE_FALLBACK.get(fmt, _SAFE_FALLBACK["horizontal"])


def caption_band(fmt: str) -> tuple[float, float]:
    """Caption band as a normalized (top, bottom) y-range from the frame top."""
    band = _safe_tokens(fmt).get("caption_band", _SAFE_FALLBACK[fmt]["caption_band"])
    return float(band[0]), float(band[1])


def platform_margins(fmt: str) -> dict[str, float]:
    """Per-edge margins as fractions of the frame (top/bottom/left/right)."""
    m = _safe_tokens(fmt).get("platform_margins", _SAFE_FALLBACK[fmt]["platform_margins"])
    return {k: float(m[k]) for k in ("top", "bottom", "left", "right")}


def resolve_safe_area_policy(scene: dict) -> tuple[bool, bool]:
    """Return ``(apply_platform_margins, apply_caption_band)`` for a scene.

    Defaults are format-derived — vertical (Shorts) reserves both; horizontal
    (long-form) reserves neither, preserving full-frame symmetry. A scene may
    override either via ``scene.safe_areas``.
    """
    fmt = scene.get("format", "horizontal")
    vertical = fmt == "vertical"
    override = (scene.get("scene") or {}).get("safe_areas")
    if not isinstance(override, dict):
        override = {}
    margins = bool(override.get("platform_margins", vertical))
    band = bool(override.get("caption_band", vertical))
    return margins, band


@lru_cache(maxsize=16)
def safe_content_rect(fmt: str, margins: bool = True, band: bool = True) -> Rect:
    """Largest rect (Manim units, origin centre, y-up) allowed by the policy:
    excludes the platform margins (when ``margins``) and sits above the caption
    band (when ``band``). With both off it is the full frame."""
    fw, fh = FRAME_BOUNDS.get(fmt, FRAME_BOUNDS["horizontal"])
    m = platform_margins(fmt) if margins else _NO_MARGINS

    left = -fw / 2.0 + m["left"] * fw
    right = fw / 2.0 - m["right"] * fw
    top = fh / 2.0 - m["top"] * fh
    bottom = -fh / 2.0 + m["bottom"] * fh

    if band:
        # A token-derived breathing gap so content clears the band edge cleanly
        # (and keeps the boundary strict against float rounding).
        from manim_renderer.theme.spacing import spacing

        band_top_norm, _band_bottom_norm = caption_band(fmt)
        band_top_manim = fh / 2.0 - band_top_norm * fh + spacing("label_gap", fmt)
        bottom = max(bottom, band_top_manim)

    return Rect(
        cx=(left + right) / 2.0,
        cy=(bottom + top) / 2.0,
        width=right - left,
        height=top - bottom,
    )


def clamp_center(
    cx: float, cy: float, w: float, h: float, fmt: str,
    margins: bool = True, band: bool = True,
) -> tuple[float, float]:
    """Shift a bbox centre so a w×h box stays inside the policy's safe rect.
    A box larger than the safe rect on an axis is centred on that axis."""
    safe = safe_content_rect(fmt, margins, band)
    left = safe.cx - safe.width / 2.0
    right = safe.cx + safe.width / 2.0
    bottom = safe.cy - safe.height / 2.0
    top = safe.cy + safe.height / 2.0
    hw, hh = w / 2.0, h / 2.0

    cx = safe.cx if 2.0 * hw >= safe.width else min(max(cx, left + hw), right - hw)
    cy = safe.cy if 2.0 * hh >= safe.height else min(max(cy, bottom + hh), top - hh)
    return cx, cy


def clamp_rect(rect: Rect, fmt: str, margins: bool = True, band: bool = True) -> Rect:
    """Return `rect` shrunk (if needed) and shifted to fit inside the policy's
    safe content rect."""
    safe = safe_content_rect(fmt, margins, band)
    w = min(rect.width, safe.width)
    h = min(rect.height, safe.height)
    cx, cy = clamp_center(rect.cx, rect.cy, w, h, fmt, margins, band)
    return Rect(cx=cx, cy=cy, width=w, height=h)

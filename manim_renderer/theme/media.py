"""Media-frame styling tokens (letterbox, border, padding, chip).

All visual constants are expressed as multiples of the format caption
line-height (see ``spacing.text_height_units``) or palette roles — no raw
hex/px in component code.
"""

from __future__ import annotations

from manim_renderer.theme.palette import UI
from manim_renderer.theme.spacing import text_height_units

# Dimensionless ratios × caption line-height → scene units.
_RATIOS: dict[str, float] = {
    "frame_stroke": 0.18,
    "corner_radius": 0.35,
    "padding": 0.28,
    "chip_pad": 0.12,
    "chip_corner": 0.06,
    "caption_gap": 0.45,
    "ken_burns_period_s": 14.0,
    "ken_burns_zoom_default": 0.08,
    "ken_burns_pan_frac": 0.12,
    "ken_burns_matte_extra": 0.25,
}

# Default frame heights (Manim units) by size role, per format.
FRAME_HEIGHT: dict[str, dict[str, float]] = {
    "horizontal": {"small": 3.0, "medium": 4.5, "large": 6.0},
    "vertical":   {"small": 4.0, "medium": 6.0, "large": 8.0},
}

_DEFAULT_ASPECT = 16 / 9

_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov", ".mkv", ".m4v"})


_TIME_SLOTS = frozenset({"ken_burns_period_s"})


def media_metric(slot: str, fmt: str = "horizontal") -> float:
    """Return a media-frame metric in scene units for ``slot``."""
    if slot not in _RATIOS:
        raise KeyError(f"unknown media token {slot!r}; available: {sorted(_RATIOS)}")
    if slot in _TIME_SLOTS:
        return _RATIOS[slot]
    return _RATIOS[slot] * text_height_units("caption", fmt)


def letterbox_color() -> str:
    """Fill color for letterbox bars (palette-derived)."""
    return UI["background"]


def frame_border_color() -> str:
    return UI["border"]


def chip_fill_color() -> str:
    return UI["surface"]


def chip_text_color() -> str:
    return UI["text_primary"]


def is_video_path(path: str) -> bool:
    from pathlib import Path
    return Path(path).suffix.lower() in _VIDEO_EXTS


# Precomputed per-format table (mirrors SPACING).
MEDIA: dict[str, dict[str, float]] = {
    fmt: {
        k: (round(media_metric(k, fmt), 4) if k != "ken_burns_period_s"
            else _RATIOS[k])
        for k in _RATIOS
    }
    for fmt in ("horizontal", "vertical")
}

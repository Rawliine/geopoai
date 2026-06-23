"""Token-derived spacing slots in Manim scene units.

Raw spacing magic numbers are banned in component code — import ``spacing()`` /
``SPACING`` from here so inter-element gaps track the brand typography tokens
instead of being hand-tuned per component.

Every gap is expressed as a multiple of the format's *caption* line-height, so
if the type scale in ``config/design_tokens.json`` changes, the gaps scale with
it. The point→scene-unit factor is a fixed Manim rendering constant (it depends
only on ``font_size``, not on output resolution — scene units are abstract);
``_UNIT_PER_PT`` was measured against Manim 0.20.x (a caption-size glyph run is
~0.0104 × font_size tall in scene units) and is a pure unit conversion, not a
brand visual constant.

Slots:
  * ``label_gap``      — text label ↔ adjacent label / strip (e.g. payoff-matrix
                         strategy labels to the grid edge).
  * ``axis_tick_gap``  — axis line / tick ↔ its tick-label band.
  * ``axis_title_gap`` — tick-label band ↔ the axis title (or a payoff-matrix
                         player name ↔ its strategy-label band).
"""

from __future__ import annotations

from manim_renderer.theme.typography import FONT_SCALE

# Manim renders a Text glyph run at a scene-unit height ≈ font_size_pt × this.
# Resolution-independent unit conversion (NOT a brand constant).
_UNIT_PER_PT = 0.0104

# Gap sizes as dimensionless multiples of the caption line-height.
_RATIOS: dict[str, float] = {
    "label_gap":      0.70,
    "axis_tick_gap":  0.55,
    # Gap from a tick-label band to its axis title (charts) / from a strategy
    # band to its player name (payoff matrix). 0.50× caption — tuned by eye so
    # the title clears the numbers without the loose look the old 1.50 gave once
    # the chart margins stopped clamping it.
    "axis_title_gap": 0.50,
}


def text_height_units(role: str, fmt: str = "horizontal") -> float:
    """Scene-unit height of a ``role``-sized text line (token-derived).

    Lets non-text components (icons, chips) size themselves relative to the brand
    type scale instead of hardcoding Manim units. ``role`` is a typography key
    (``title`` / ``body`` / ``label`` / ``caption``)."""
    scale = FONT_SCALE.get(fmt, FONT_SCALE["horizontal"])
    return scale.get(role, scale["caption"]) * _UNIT_PER_PT


def _caption_unit(fmt: str) -> float:
    """Caption text height for ``fmt`` in scene units (token-derived)."""
    return text_height_units("caption", fmt)


def spacing(slot: str, fmt: str = "horizontal") -> float:
    """Gap for ``slot`` in scene units, scaled to the format's caption type."""
    if slot not in _RATIOS:
        raise KeyError(
            f"unknown spacing slot {slot!r}; available: {sorted(_RATIOS)}"
        )
    return _RATIOS[slot] * _caption_unit(fmt)


# Precomputed per-format table for dict-style access (mirrors FONT_SCALE/TIMING).
SPACING: dict[str, dict[str, float]] = {
    fmt: {slot: round(spacing(slot, fmt), 4) for slot in _RATIOS}
    for fmt in ("horizontal", "vertical")
}

"""Slot-aware text fitting — shared helper for any component bearing text.

The scene runner passes `_slot_bounds: (width, height)` in params when a
component is placed in a slot. Components rendering text should call
`auto_fit_text` to scale the text down if it would overflow the slot.

Why scaling vs. wrapping: titles read better as single lines. Wrapping a
title to two lines changes its visual identity. Scale-down preserves the
single-line title feel and matches editorial conventions (where titles
shrink to fit, not wrap).

For multi-line annotation text (CalloutBox), wrap is the right approach —
that lives in the component itself, not here.
"""

from __future__ import annotations

from manim import Text


def auto_fit_text(
    text: str,
    *,
    font: str,
    font_size: int,
    color: str,
    target_width: float | None,
    target_height: float | None = None,
    margin: float = 0.92,
    min_scale: float = 0.4,
    **text_kwargs,
) -> Text:
    """Build a Text mobject that fits within target bounds.

    Builds at the requested `font_size`. If the rendered text exceeds either
    `target_width × margin` or `target_height × margin`, scales the mobject
    down to fit (clamped at `min_scale` of the original size).

    Args:
        text: the string to render.
        font: font family.
        font_size: requested point size before any auto-fit.
        color: hex color.
        target_width: max width in Manim units, or None to skip width fit.
        target_height: max height in Manim units, or None to skip height fit.
        margin: fraction of target the text may use (default 0.92 = 8% gutter).
        min_scale: lower bound on the scale factor — never shrink below this
            fraction of the requested font_size, even if the text still
            overflows. Prevents text from becoming illegibly small.
        **text_kwargs: forwarded to Text (e.g. weight, line_spacing).

    Returns:
        A Text mobject sized to fit (or as close as min_scale allows).
    """
    mob = Text(text, font=font, font_size=font_size, color=color, **text_kwargs)

    scale_w = 1.0
    scale_h = 1.0
    if target_width is not None and mob.width > target_width * margin:
        scale_w = (target_width * margin) / mob.width
    if target_height is not None and mob.height > target_height * margin:
        scale_h = (target_height * margin) / mob.height

    scale = min(scale_w, scale_h)
    if scale < 1.0:
        scale = max(scale, min_scale)
        mob.scale(scale)

    return mob

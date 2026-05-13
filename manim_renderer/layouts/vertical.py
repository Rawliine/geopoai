"""Vertical (9:16) layouts. Manim frame: 8.0w × 14.2h, origin at center.

Vertical twins of horizontal layouts use the same slot names where they map
1:1, but the layout *name* differs (e.g., horizontal `split` → vertical
`stacked`). The runtime picks by (format, layout_name); JSON authors must use
the right pair.
"""

from manim_renderer.layouts.base import Layout, Rect

VERTICAL_LAYOUTS: dict[str, Layout] = {
    # Single centered slot.
    "hero": Layout(
        name="hero",
        format="vertical",
        slots={
            "main": Rect(cx=0.0, cy=0.0, width=6.5, height=12.0),
        },
    ),

    # Vertical twin of "split" — top + bottom.
    "stacked": Layout(
        name="stacked",
        format="vertical",
        slots={
            "top":    Rect(cx=0.0, cy= 3.4, width=6.5, height=6.0),
            "bottom": Rect(cx=0.0, cy=-3.4, width=6.5, height=6.0),
        },
    ),

    # Vertical twin of "data-left". Data on top, body below.
    "data-top": Layout(
        name="data-top",
        format="vertical",
        slots={
            "data": Rect(cx=0.0, cy= 4.5, width=6.5, height=4.0),
            "body": Rect(cx=0.0, cy=-2.0, width=6.5, height=8.5),
        },
    ),

    # Vertical twin of "trio" — three rows.
    "trio-stack": Layout(
        name="trio-stack",
        format="vertical",
        slots={
            "A": Rect(cx=0.0, cy= 4.5, width=6.5, height=4.0),
            "B": Rect(cx=0.0, cy= 0.0, width=6.5, height=4.0),
            "C": Rect(cx=0.0, cy=-4.5, width=6.5, height=4.0),
        },
    ),

    # Title-body works in both formats.
    "title-body": Layout(
        name="title-body",
        format="vertical",
        slots={
            "title": Rect(cx=0.0, cy= 6.0, width=6.5, height=1.5),
            "body":  Rect(cx=0.0, cy=-1.0, width=6.5, height=11.5),
        },
    ),
}

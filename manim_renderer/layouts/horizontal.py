"""Horizontal (16:9) layouts. Manim frame: 14.2w × 8.0h, origin at center.

Slot rects are in unit space (frame center is origin, y-up). All slot bounds
must fit within the frame; `tests/layouts/test_layouts.py` enforces this.
"""

from manim_renderer.layouts.base import Layout, Rect

HORIZONTAL_LAYOUTS: dict[str, Layout] = {
    # Single centered slot. Default for any scene with one focal element.
    "hero": Layout(
        name="hero",
        format="horizontal",
        slots={
            "main": Rect(cx=0.0, cy=0.0, width=12.0, height=6.0),
        },
    ),

    # Two side-by-side slots. Vertical twin: "stacked".
    "split": Layout(
        name="split",
        format="horizontal",
        slots={
            "left":  Rect(cx=-3.4, cy=0.0, width=6.0, height=6.5),
            "right": Rect(cx= 3.4, cy=0.0, width=6.0, height=6.5),
        },
    ),

    # Narrow data panel on the left + wider body on the right.
    # Vertical twin: "data-top".
    "data-left": Layout(
        name="data-left",
        format="horizontal",
        slots={
            "data": Rect(cx=-4.4, cy=0.0, width=4.5, height=6.5),
            "body": Rect(cx= 2.0, cy=0.0, width=8.5, height=6.5),
        },
    ),

    # Three columns. Vertical twin: "trio-stack".
    "trio": Layout(
        name="trio",
        format="horizontal",
        slots={
            "A": Rect(cx=-4.5, cy=0.0, width=4.0, height=6.5),
            "B": Rect(cx= 0.0, cy=0.0, width=4.0, height=6.5),
            "C": Rect(cx= 4.5, cy=0.0, width=4.0, height=6.5),
        },
    ),

    # Title strip + body. Works in both formats (vertical version below).
    "title-body": Layout(
        name="title-body",
        format="horizontal",
        slots={
            "title": Rect(cx=0.0, cy= 3.0, width=12.0, height=1.5),
            "body":  Rect(cx=0.0, cy=-1.0, width=12.0, height=5.5),
        },
    ),
}

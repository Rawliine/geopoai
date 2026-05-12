"""Vertical (9:16) layouts. Manim frame: 8.0w × 14.2h, origin at center."""

from manim_renderer.layouts.base import Layout, Rect

VERTICAL_LAYOUTS: dict[str, Layout] = {
    "hero": Layout(
        name="hero",
        format="vertical",
        slots={
            "main": Rect(cx=0.0, cy=0.0, width=6.5, height=12.0),
        },
    ),
}

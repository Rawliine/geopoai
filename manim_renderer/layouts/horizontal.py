"""Horizontal (16:9) layouts. Manim frame: 14.2w × 8.0h, origin at center."""

from manim_renderer.layouts.base import Layout, Rect

HORIZONTAL_LAYOUTS: dict[str, Layout] = {
    "hero": Layout(
        name="hero",
        format="horizontal",
        slots={
            "main": Rect(cx=0.0, cy=0.0, width=12.0, height=6.0),
        },
    ),
}

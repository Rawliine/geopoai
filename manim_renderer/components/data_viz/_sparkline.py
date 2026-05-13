"""Sparkline — tiny inline trend chart used by StatBlock and (future) tables.

A sparkline is a stripped-down line chart: no axes, no labels, no gridlines —
just a single line through normalized points sized to fit a small unit-rect.
Editorial convention: minimum-marker (small dot at min), maximum-marker (small
dot at max), end-marker (small dot at last point). All toggleable.

Not a `BaseComponent` — used only as a subcomponent inside other components.
Lives in `_sparkline.py` so the leading underscore signals "not for direct use
from a JSON action."
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from manim import VGroup, VMobject, Dot, Line, RIGHT

from manim_renderer.theme.palette import SEMANTIC, UI


# Visual defaults
_DEFAULT_STROKE = 2.5
_MARKER_RADIUS = 0.06
_BASELINE_OPACITY = 0.25


class Sparkline(VGroup):
    """Build a sparkline from numeric series.

    Args:
        series: list of numeric values (≥2 points required).
        size: (width, height) of the sparkline rect in Manim units.
        line_color: hex color for the trend line.
        marker_color: hex color for end/min/max dots (defaults to line_color).
        baseline_color: faint baseline (last value extended back); None to omit.
        show_end_marker: dot at the last point.
        show_extrema_markers: dots at min and max points.
        zero_baseline: if True, normalize so 0.0 sits at the bottom rather than
            the series min. Useful for comparable-magnitude charts.
    """

    def __init__(
        self,
        series: Sequence[float],
        *,
        size: tuple[float, float] = (1.5, 0.5),
        line_color: str = SEMANTIC["highlight"],
        marker_color: str | None = None,
        baseline_color: str | None = UI["text_secondary"],
        show_end_marker: bool = True,
        show_extrema_markers: bool = False,
        zero_baseline: bool = False,
        stroke_width: float = _DEFAULT_STROKE,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if len(series) < 2:
            raise ValueError(
                f"Sparkline needs at least 2 points; got {len(series)}"
            )

        width, height = size
        marker_color = marker_color or line_color

        # Normalize series to local-space points: x in [0, width], y in [0, height].
        # Y-baseline is min(series) (or 0 if zero_baseline).
        n = len(series)
        xs = np.linspace(0.0, width, n)
        y_min = 0.0 if zero_baseline else float(min(series))
        y_max = float(max(series))
        if y_max == y_min:
            y_max = y_min + 1.0  # flat series -> arbitrary midline
        ys = np.array([
            (v - y_min) / (y_max - y_min) * height for v in series
        ])

        points = [np.array([x, y, 0.0]) for x, y in zip(xs, ys)]

        # Optional baseline (faint horizontal line at the y_min level).
        if baseline_color is not None:
            baseline = Line(
                start=np.array([0.0, 0.0, 0.0]),
                end=np.array([width, 0.0, 0.0]),
                color=baseline_color,
                stroke_width=1.0,
                stroke_opacity=_BASELINE_OPACITY,
            )
            self.add(baseline)

        # The trend line itself.
        line = VMobject(stroke_color=line_color, stroke_width=stroke_width)
        line.set_points_as_corners(points)
        self.add(line)

        # Markers.
        if show_extrema_markers:
            min_idx = int(np.argmin(ys))
            max_idx = int(np.argmax(ys))
            for idx in {min_idx, max_idx}:
                self.add(
                    Dot(points[idx], radius=_MARKER_RADIUS, color=marker_color)
                )
        if show_end_marker:
            self.add(
                Dot(points[-1], radius=_MARKER_RADIUS, color=marker_color)
            )

        # Position: center the whole sparkline at origin so callers can move_to()
        # arbitrary positions.
        self.move_to([0.0, 0.0, 0.0])

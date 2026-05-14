"""LineChart — continuous multi-series line chart.

Reuses `_axes_common.Axes2D` (continuous x mode). Series are rendered as
themed polylines with optional point markers. `draw-out` is the canonical
entrance — `Create()` animates the path being drawn left-to-right.

Schema-allowed effects (see show_line_chart.json):
  fade-in (default), draw-out, level-by-level

Custom anchors:
  * `series:<i_or_label>.end`   — end of series' polyline (right-most point)
  * `series:<i_or_label>.start` — start of polyline

```json
{
  "action": "showLineChart",
  "params": {
    "id": "trade",
    "series": [
      {"label": "USA",   "color": "actor_a",
       "points": [[2010, 14], [2020, 21]]},
      {"label": "China", "color": "actor_b",
       "points": [[2010, 6],  [2020, 17]]}
    ],
    "size": "medium",
    "x_axis": {"min": 2010, "max": 2020, "label": "Year"},
    "y_axis": {"min": 0, "max": 25, "label": "GDP ($T)"},
    "value_format": "decimal",
    "effect": "draw-out", "timing": "slow"
  }
}
```

Points are `[x, y]` arrays (not `{"x": ..., "y": ...}`) to keep the
JSON-wide "no coordinate keys" rule (AGENT.md rule 1) simple — the
validator's coords-banned tier rejects `x`/`y` keys anywhere in the JSON,
including data values.
"""

from __future__ import annotations

import numpy as np
from manim import (
    AnimationGroup,
    Create,
    Dot,
    FadeIn,
    LaggedStart,
    ORIGIN,
    VGroup,
    VMobject,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.components.data_viz._axes_common import Axes2D
from manim_renderer.components.data_viz._value_format import VALUE_FORMATS
from manim_renderer.resolvers.size import resolve_size
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import STAGGER, TIMING


_PALETTE: dict[str, str] = {**ACTORS, **SEMANTIC, **UI}

_DEFAULT_COLOR_CYCLE = ["actor_a", "actor_b", "actor_c", "actor_d", "actor_e"]

_LINE_STROKE_WIDTH = 3.0
_POINT_RADIUS = 0.07


def _resolve_color(key: str | None, fallback: str) -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


class LineChart(BaseComponent):
    """Multi-series continuous-x line chart with themed axes."""

    SIZE_KIND = "chart"

    def build(self) -> None:
        p = self.params

        series = p.get("series")
        if not series or not isinstance(series, list):
            raise ValueError("LineChart requires non-empty params.series list")

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="chart")

        # Materialize series.
        self._series_labels: list[str] = []
        self._series_points: list[list[tuple[float, float]]] = []
        self._series_colors: list[str] = []
        for i, s in enumerate(series):
            pts = s.get("points") or []
            if len(pts) < 2:
                raise ValueError(
                    f"LineChart series[{i}] needs at least 2 points; got {len(pts)}"
                )
            self._series_labels.append(str(s.get("label", f"series_{i}")))
            self._series_points.append(
                [(float(pt[0]), float(pt[1])) for pt in pts]
            )
            self._series_colors.append(
                _resolve_color(
                    s.get("color"),
                    fallback=_DEFAULT_COLOR_CYCLE[i % len(_DEFAULT_COLOR_CYCLE)],
                )
            )

        # Axis ranges — explicit overrides win; otherwise auto from union of points.
        x_axis = p.get("x_axis", {})
        y_axis = p.get("y_axis", {})
        all_xs = [x for series_pts in self._series_points for x, _ in series_pts]
        all_ys = [y for series_pts in self._series_points for _, y in series_pts]
        x_min = float(x_axis.get("min", min(all_xs)))
        x_max = float(x_axis.get("max", max(all_xs)))
        y_pad = max(1e-6, (max(all_ys) - min(all_ys)) * 0.05)
        y_min = float(y_axis.get("min", min(all_ys) - y_pad))
        y_max = float(y_axis.get("max", max(all_ys) + y_pad))

        self._value_format = p.get("value_format", "int")
        if self._value_format not in VALUE_FORMATS:
            raise ValueError(
                f"unknown value_format {self._value_format!r}; "
                f"available: {VALUE_FORMATS}"
            )
        self._format_opts = {
            k: v for k, v in p.items()
            if k in ("decimals", "symbol", "suffix")
        }

        x_format = p.get("x_format", "int")
        self._show_points = bool(p.get("show_points", True))

        # Build axes.
        self._axes = Axes2D(
            width=width,
            height=height,
            format=self.format,
            y_min=y_min,
            y_max=y_max,
            y_format=self._value_format,
            y_format_opts=self._format_opts,
            y_ticks=int(y_axis.get("ticks", 4)),
            y_label=y_axis.get("label"),
            x_min=x_min,
            x_max=x_max,
            x_format=x_format,
            x_ticks=int(x_axis.get("ticks", 4)),
            x_label=x_axis.get("label"),
        )
        self.add(self._axes)

        # Build polylines + (optional) markers per series.
        self._lines: list[VMobject] = []
        self._series_markers: list[list[Dot]] = []
        self._series_local_points: list[list[np.ndarray]] = []

        for points, hex_color in zip(self._series_points, self._series_colors):
            local_pts = [
                np.array(
                    [self._axes.value_to_x(x), self._axes.value_to_y(y), 0.0]
                )
                for x, y in points
            ]
            self._series_local_points.append(local_pts)

            line = VMobject(stroke_color=hex_color, stroke_width=_LINE_STROKE_WIDTH)
            line.set_points_as_corners(local_pts)
            self._lines.append(line)
            self.add(line)

            if self._show_points:
                dots = [Dot(pt, radius=_POINT_RADIUS, color=hex_color) for pt in local_pts]
                self._series_markers.append(dots)
                for dot in dots:
                    self.add(dot)
            else:
                self._series_markers.append([])

        self.move_to(ORIGIN)

    # --- bespoke entrance ----------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "draw-out":
            run_time = TIMING[timing]
            # Axes fade in fast; lines draw out; markers fade in after.
            axes_anim = FadeIn(self._axes, run_time=TIMING["fast"])
            line_anims = [Create(line, run_time=run_time) for line in self._lines]
            parts = [axes_anim, *line_anims]
            marker_mobs = [dot for dots in self._series_markers for dot in dots]
            if marker_mobs:
                parts.append(FadeIn(VGroup(*marker_mobs), run_time=TIMING["fast"]))
            return AnimationGroup(*parts)

        if effect == "level-by-level":
            # Reveal each series in sequence: axes, then series 1, then series 2…
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])
            series_groups = []
            for line, dots in zip(self._lines, self._series_markers):
                if dots:
                    series_groups.append(VGroup(line, *dots))
                else:
                    series_groups.append(line)
            axes_anim = FadeIn(self._axes, run_time=TIMING["fast"])
            lagged = LaggedStart(
                *(FadeIn(g) for g in series_groups),
                lag_ratio=lag,
                run_time=run_time,
            )
            return AnimationGroup(axes_anim, lagged)

        return super().entrance(effect, timing, **extra)

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_series(self, arg: str) -> np.ndarray:
        """`series:<i_or_label>.<start|end>` -> that endpoint."""
        ident, sep, which = arg.partition(".")
        if not sep:
            raise KeyError(
                f"LineChart `series:{arg}` needs '.start' or '.end' suffix "
                f"(e.g. 'series:0.end' or 'series:USA.start')"
            )
        if which not in ("start", "end"):
            raise KeyError(
                f"LineChart `series:{arg}` suffix must be 'start' or 'end'; got {which!r}"
            )
        idx = self._lookup_series_index(ident)
        line = self._lines[idx]
        # get_start/get_end track the moved mobject, so this anchor works after
        # the scene runner calls move_to() on the chart.
        return np.asarray(line.get_start() if which == "start" else line.get_end())

    def _lookup_series_index(self, ident: str) -> int:
        if ident.isdigit():
            i = int(ident)
            if not 0 <= i < len(self._lines):
                raise KeyError(
                    f"LineChart `series:{ident}` out of range [0, {len(self._lines)})"
                )
            return i
        if ident in self._series_labels:
            return self._series_labels.index(ident)
        raise KeyError(
            f"LineChart has no series with label={ident!r}; "
            f"available indices 0..{len(self._lines)-1}, labels: {self._series_labels}"
        )

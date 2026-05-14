"""BarChart — categorical bars with axes, palette colors, and value labels.

The first proper data-viz component to use the shared `_axes_common` layer.
Validates:
  * Axes2D plot-area math for both formats
  * Per-bar palette color rotation
  * count-up entrance using CountUpAnimation on a per-bar value label
  * `bar:<i_or_label>` custom anchor (used by overlays/callouts)

Schema-allowed effects (see show_bar_chart.json):
  fade-in (default), grow-up, level-by-level, count-up

Custom anchors:
  * `bar:<i_or_label>` — top-center of bar i (or labeled bar). 0-based indexing.

```json
{
  "action": "showBarChart",
  "params": {
    "id": "gdp",
    "data": [
      {"label": "USA",   "value": 23000, "color": "actor_a"},
      {"label": "China", "value": 17000, "color": "actor_b"}
    ],
    "size": "medium",
    "y_axis": {"min": 0, "max": 25000, "ticks": 5, "label": "GDP ($B)"},
    "value_format": "k",
    "show_value_labels": true,
    "effect": "count-up", "timing": "slow"
  }
}
```
"""

from __future__ import annotations

import numpy as np
from manim import (
    AnimationGroup,
    DOWN,
    FadeIn,
    GrowFromEdge,
    LaggedStart,
    ORIGIN,
    Rectangle,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.components.data_viz._axes_common import Axes2D
from manim_renderer.components.data_viz._value_format import (
    VALUE_FORMATS,
    format_value,
)
from manim_renderer.effects._animations import CountUpAnimation
from manim_renderer.resolvers.size import resolve_size
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import STAGGER, TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


_PALETTE: dict[str, str] = {**ACTORS, **SEMANTIC, **UI}

# Default color rotation when a data point omits `color`.
_DEFAULT_COLOR_CYCLE = ["actor_a", "actor_b", "actor_c", "actor_d", "actor_e"]

# Bar width as a fraction of its slot (rest is gap).
_BAR_WIDTH_RATIO = 0.7

# Value-label vertical offset above bar top.
_VALUE_LABEL_BUFF = 0.10


def _resolve_color(key: str | None, fallback: str) -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


class _BarValueLabel(VGroup):
    """Re-renderable numeric label above a bar. Implements `set_value` so
    `CountUpAnimation` can drive it during the count-up entrance.

    Stays pinned to a fixed anchor point (the bar's full-height top) so the
    text doesn't drift as the rendered string changes width.
    """

    def __init__(
        self,
        value: float,
        *,
        value_format: str,
        format_opts: dict,
        font: str,
        font_size: int,
        color: str,
        anchor_point: np.ndarray,
    ):
        super().__init__()
        self._value_format = value_format
        self._format_opts = format_opts
        self._font = font
        self._font_size = font_size
        self._color = color
        self._anchor_point = np.asarray(anchor_point, dtype=float)
        self._text = self._render(value)
        self._text.move_to(self._anchor_point)
        self.add(self._text)

    def _render(self, value: float) -> Text:
        return Text(
            format_value(value, self._value_format, **self._format_opts),
            font=self._font,
            font_size=self._font_size,
            color=self._color,
        )

    def set_value(self, value: float) -> None:
        new_text = self._render(value)
        new_text.move_to(self._anchor_point)
        self.remove(self._text)
        self._text = new_text
        self.add(self._text)


class BarChart(BaseComponent):
    """Categorical bars with themed axes."""

    SIZE_KIND = "chart"

    def build(self) -> None:
        p = self.params

        data = p.get("data")
        if not data or not isinstance(data, list):
            raise ValueError("BarChart requires non-empty params.data list")

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="chart")

        self._labels = [str(d["label"]) for d in data]
        self._values = [float(d["value"]) for d in data]
        self._colors = [
            _resolve_color(
                d.get("color"),
                fallback=_DEFAULT_COLOR_CYCLE[i % len(_DEFAULT_COLOR_CYCLE)],
            )
            for i, d in enumerate(data)
        ]

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

        # Axis config: auto-range if omitted. Bar charts start from 0 by
        # convention (truncated y-axis = editorial sin in news/analysis viz).
        y_axis = p.get("y_axis", {})
        y_max = float(y_axis.get("max", max(self._values) * 1.15))
        y_min = float(y_axis.get("min", 0.0))
        y_ticks = int(y_axis.get("ticks", 4))
        y_label = y_axis.get("label")
        x_label = p.get("x_axis", {}).get("label")

        self._show_value_labels = bool(p.get("show_value_labels", True))

        # Build axes.
        self._axes = Axes2D(
            width=width,
            height=height,
            format=self.format,
            y_min=y_min,
            y_max=y_max,
            y_format=self._value_format,
            y_format_opts=self._format_opts,
            y_ticks=y_ticks,
            y_label=y_label,
            x_categories=self._labels,
            x_label=x_label,
        )
        self.add(self._axes)

        # Build bars + value labels.
        plot = self._axes.plot
        slot_w = plot.width / len(data)
        bar_w = slot_w * _BAR_WIDTH_RATIO
        baseline_y = self._axes.value_to_y(max(0.0, y_min))

        self._bars: list[Rectangle] = []
        self._value_labels: list[_BarValueLabel] = []
        label_font_size = int(FONT_SCALE[self.format]["caption"] * 0.85)

        for i, (val, hex_color) in enumerate(zip(self._values, self._colors)):
            cx = self._axes.category_to_x(i)
            top_y = self._axes.value_to_y(val)
            bar_h = top_y - baseline_y
            bar = Rectangle(
                width=bar_w,
                height=max(abs(bar_h), 1e-6),
                color=hex_color,
                fill_color=hex_color,
                fill_opacity=0.85,
                stroke_width=1.5,
            )
            # Anchor the bar so its bottom edge sits at the baseline.
            bar.move_to(np.array([cx, baseline_y + bar_h / 2, 0.0]))
            self._bars.append(bar)
            self.add(bar)

            if self._show_value_labels:
                label = _BarValueLabel(
                    val,
                    value_format=self._value_format,
                    format_opts=self._format_opts,
                    font=FONTS["primary"],
                    font_size=label_font_size,
                    color=UI["text_primary"],
                    anchor_point=np.array([cx, top_y + _VALUE_LABEL_BUFF + 0.05, 0.0]),
                )
                self._value_labels.append(label)
                self.add(label)

        self.move_to(ORIGIN)

    # --- bespoke entrance: bars grow + value labels count up ----------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "count-up":
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])
            child_anims = []
            for bar, value, label in zip(
                self._bars,
                self._values,
                self._value_labels or [None] * len(self._bars),
            ):
                bar_anim = GrowFromEdge(bar, DOWN, run_time=run_time)
                if label is None:
                    child_anims.append(bar_anim)
                else:
                    # Snap label to start value so the count-up looks right.
                    label.set_value(0)
                    count = CountUpAnimation(
                        label,
                        start_value=0,
                        target_value=value,
                        run_time=run_time,
                    )
                    child_anims.append(AnimationGroup(bar_anim, count))
            # Axes appear instantly underneath the bars.
            axes_anim = FadeIn(self._axes, run_time=TIMING["fast"])
            bars_lagged = LaggedStart(
                *child_anims,
                lag_ratio=lag,
                run_time=run_time,
            )
            return AnimationGroup(axes_anim, bars_lagged)
        if effect == "grow-up":
            # Bars grow simultaneously; axes fade in.
            run_time = TIMING[timing]
            bar_anims = [GrowFromEdge(b, DOWN, run_time=run_time) for b in self._bars]
            axes_anim = FadeIn(self._axes, run_time=TIMING["fast"])
            label_anim = (
                FadeIn(VGroup(*self._value_labels), run_time=run_time)
                if self._value_labels else None
            )
            parts = [axes_anim, *bar_anims]
            if label_anim is not None:
                parts.append(label_anim)
            return AnimationGroup(*parts)
        return super().entrance(effect, timing, **extra)

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_bar(self, arg: str) -> np.ndarray:
        """`bar:<i_or_label>` -> top-center of that bar."""
        idx = self._lookup_bar_index(arg)
        return self._bars[idx].get_top()

    def _lookup_bar_index(self, arg: str) -> int:
        if arg.isdigit():
            i = int(arg)
            if not 0 <= i < len(self._bars):
                raise KeyError(
                    f"BarChart `bar:{arg}` out of range [0, {len(self._bars)})"
                )
            return i
        if arg in self._labels:
            return self._labels.index(arg)
        raise KeyError(
            f"BarChart has no bar with label={arg!r}; "
            f"available indices 0..{len(self._bars)-1}, labels: {self._labels}"
        )

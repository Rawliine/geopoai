"""Shared axes primitives for BarChart and LineChart (private).

Why a shared helper: both charts need a plot area, themed axis lines, themed
tick labels formatted via `_value_format`, and data-to-screen coordinate
mappers. Without sharing, the two components would duplicate ~150 lines of
margin math and tick rendering — and would drift visually over time.

Design choices (locked):

* **Fixed conservative margins** for Phase 1. Dynamic margins (auto-grow when
  the y-axis label is long) is a follow-up — chart legibility doesn't suffer
  with the fixed values and the math stays trivially testable.
* **Pure-math layer + Manim layer** kept separate. `PlotArea` is the pure
  geometry (no mobjects), `Axes2D` is the VGroup that uses it. The unit tests
  exercise `PlotArea` without any Manim render.
* **"Nice" tick steps via 1/2/5×10^k.** Standard editorial convention; gives
  human-readable axis values without ever needing the LLM to specify ticks
  manually. The author still overrides via `y_axis.ticks` if needed.
* **Categorical x for bars, continuous x for lines** share the same `Axes2D` —
  the difference is which mapper is used and whether x-tick labels come from
  data labels (bars) or formatted values (lines).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from manim import Line, Text, VGroup

from manim_renderer.components.data_viz._value_format import format_value
from manim_renderer.theme.palette import UI
from manim_renderer.theme.typography import FONTS, FONT_SCALE


# Plot-area margins as fractions of total bbox. Tuned for both formats.
# Extra padding added on the side that has an axis title.
_MARGIN_LEFT_BASE = 0.12
_MARGIN_RIGHT = 0.04
_MARGIN_TOP = 0.06
_MARGIN_BOTTOM_BASE = 0.14
_AXIS_TITLE_EXTRA = 0.05  # added if that axis has a title

_AXIS_STROKE_WIDTH = 1.5
_TICK_LENGTH = 0.08
_TICK_LABEL_BUFF = 0.10
# Buff between the tick-label band and the axis title. Titles are now
# positioned RELATIVE to the tick-label band (not the bbox edge), so this
# constant directly controls the visible gap users perceive between e.g.
# the y-tick numbers ("80", "60") and the axis title ("%").
_AXIS_TITLE_BUFF = 0.30

# Default number of ticks if `y_axis.ticks` is omitted.
_DEFAULT_Y_TICKS = 4
_DEFAULT_X_TICKS = 4


@dataclass(frozen=True)
class PlotArea:
    """Pure geometry of a plot area in component-local coordinates.

    Origin is the chart's bounding-box center; the plot area sits asymmetric
    inside the bbox because axes/labels eat into the left/bottom margins.

    Fields are local-space (the parent VGroup later does its own `move_to`).
    """

    bbox_width: float
    bbox_height: float
    left: float    # plot-area left edge x
    right: float   # plot-area right edge x
    bottom: float  # plot-area bottom edge y
    top: float     # plot-area top edge y

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center(self) -> np.ndarray:
        return np.array(
            [(self.left + self.right) / 2, (self.bottom + self.top) / 2, 0.0]
        )


def compute_plot_area(
    width: float,
    height: float,
    *,
    has_y_title: bool = False,
    has_x_title: bool = False,
) -> PlotArea:
    """Carve out the plot-area rect from the bbox. Bbox is centered at origin."""
    left_margin = _MARGIN_LEFT_BASE + (_AXIS_TITLE_EXTRA if has_y_title else 0.0)
    bottom_margin = _MARGIN_BOTTOM_BASE + (_AXIS_TITLE_EXTRA if has_x_title else 0.0)

    half_w = width / 2
    half_h = height / 2
    left = -half_w + width * left_margin
    right = half_w - width * _MARGIN_RIGHT
    bottom = -half_h + height * bottom_margin
    top = half_h - height * _MARGIN_TOP
    return PlotArea(width, height, left, right, bottom, top)


# --- value mappers -----------------------------------------------------------


def make_value_to_y(plot: PlotArea, y_min: float, y_max: float):
    """Closure: continuous value in [y_min, y_max] -> local y coord.

    Clamps at edges if asked outside range (defensive against off-axis data).
    """
    if y_max == y_min:
        # Degenerate: pin everything at the midline.
        mid = (plot.bottom + plot.top) / 2
        return lambda v: mid
    plot_bottom = plot.bottom
    plot_top = plot.top
    span = y_max - y_min

    def to_y(v: float) -> float:
        return plot_bottom + (v - y_min) / span * (plot_top - plot_bottom)

    return to_y


def make_value_to_x(plot: PlotArea, x_min: float, x_max: float):
    """Closure: continuous value in [x_min, x_max] -> local x coord."""
    if x_max == x_min:
        mid = (plot.left + plot.right) / 2
        return lambda v: mid
    plot_left = plot.left
    plot_right = plot.right
    span = x_max - x_min

    def to_x(v: float) -> float:
        return plot_left + (v - x_min) / span * (plot_right - plot_left)

    return to_x


def make_category_to_x(plot: PlotArea, n_categories: int):
    """Closure: bar index (0..n-1) -> local x coord at the bar's CENTER.

    Bars are evenly spaced across the plot area; the first bar's center sits
    half a slot in from `plot.left`.
    """
    if n_categories <= 0:
        raise ValueError("n_categories must be >= 1")
    slot_w = plot.width / n_categories
    base = plot.left + slot_w / 2

    def to_x(i: int) -> float:
        return base + i * slot_w

    return to_x


# --- "nice" tick step --------------------------------------------------------


def nice_ticks(v_min: float, v_max: float, target_count: int) -> list[float]:
    """Pick ~target_count ticks at "nice" values across [v_min, v_max].

    "Nice" = step is 1/2/5 × 10^k. Always includes endpoints if they happen
    to land on a tick.

    Returns sorted list of tick values.
    """
    if target_count < 1:
        raise ValueError("target_count must be >= 1")
    if v_max < v_min:
        v_min, v_max = v_max, v_min
    if v_max == v_min:
        return [v_min]

    span = v_max - v_min
    raw_step = span / target_count
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    if residual < 1.5:
        step = 1 * magnitude
    elif residual < 3.5:
        step = 2 * magnitude
    elif residual < 7.5:
        step = 5 * magnitude
    else:
        step = 10 * magnitude

    first = math.ceil(v_min / step) * step
    ticks: list[float] = []
    # Cap to avoid runaway loops on pathological floats.
    for k in range(target_count * 4 + 2):
        v = first + k * step
        if v > v_max + step * 1e-9:
            break
        # Clean up float noise so 0.30000000000001 -> 0.3 in tick labels.
        ticks.append(round(v, 10))
    return ticks


# --- the renderable axes -----------------------------------------------------


class Axes2D(VGroup):
    """Themed plot-area frame: y-axis line + ticks + labels, x-axis line +
    labels (categorical or continuous), optional axis titles.

    Sized in unit-space (caller passes width/height from `resolve_size`).
    Constructed at origin; the parent component places the whole VGroup.

    Args:
        width, height: bbox in Manim units.
        format: 'horizontal' | 'vertical' — drives font sizing.
        y_min, y_max: y-axis range (always continuous).
        y_format: value_format key for y-tick labels (default 'int').
        y_format_opts: extra kwargs forwarded to the formatter (e.g. decimals).
        y_ticks: number of y-ticks (passed to nice_ticks).
        y_label: optional axis title text (left of plot, rotated 90°).
        x_categories: list of bar labels for categorical x; None for continuous.
        x_min, x_max: continuous x-axis range (ignored if x_categories set).
        x_format, x_format_opts, x_ticks: same shape as y_ on the x-axis.
        x_label: optional x-axis title.
    """

    def __init__(
        self,
        width: float,
        height: float,
        *,
        format: str = "horizontal",
        y_min: float,
        y_max: float,
        y_format: str = "int",
        y_format_opts: dict | None = None,
        y_ticks: int = _DEFAULT_Y_TICKS,
        y_label: str | None = None,
        x_categories: list[str] | None = None,
        x_min: float | None = None,
        x_max: float | None = None,
        x_format: str = "int",
        x_format_opts: dict | None = None,
        x_ticks: int = _DEFAULT_X_TICKS,
        x_label: str | None = None,
    ):
        super().__init__()
        self._format = format
        self._y_format = y_format
        self._y_format_opts = y_format_opts or {}
        self._x_format = x_format
        self._x_format_opts = x_format_opts or {}

        self.plot = compute_plot_area(
            width, height,
            has_y_title=y_label is not None,
            has_x_title=x_label is not None,
        )

        self.y_min, self.y_max = y_min, y_max
        self.value_to_y = make_value_to_y(self.plot, y_min, y_max)

        if x_categories is not None:
            self._categorical = True
            self.x_categories = list(x_categories)
            self.category_to_x = make_category_to_x(self.plot, len(self.x_categories))
            self.x_min = self.x_max = None
            self.value_to_x = None
        else:
            if x_min is None or x_max is None:
                raise ValueError(
                    "Axes2D continuous mode requires x_min and x_max "
                    "(or pass x_categories for bar-chart mode)"
                )
            self._categorical = False
            self.x_min, self.x_max = x_min, x_max
            self.value_to_x = make_value_to_x(self.plot, x_min, x_max)
            self.category_to_x = None
            self.x_categories = None

        # Build the visible parts.
        self._build_axis_lines()
        self._build_y_ticks(y_ticks)
        self._build_x_labels(x_ticks)
        if y_label:
            self._build_y_title(y_label)
        if x_label:
            self._build_x_title(x_label)

    # --- private builders ----------------------------------------------------

    def _tick_font_size(self) -> int:
        # caption-class font for tick labels, slightly smaller than caption.
        return int(FONT_SCALE[self._format]["caption"] * 0.78)

    def _title_font_size(self) -> int:
        # Axis titles ("Payoff", "Outcome", etc.).
        # reduced from caption*0.95 to caption*0.75 so
        # titles read clearly on small charts without dominating ~9% of
        # chart height each.
        return int(FONT_SCALE[self._format]["caption"] * 0.75)

    def _build_axis_lines(self) -> None:
        color = UI["border"]
        x_axis = Line(
            start=np.array([self.plot.left, self.plot.bottom, 0.0]),
            end=np.array([self.plot.right, self.plot.bottom, 0.0]),
            color=color,
            stroke_width=_AXIS_STROKE_WIDTH,
        )
        y_axis = Line(
            start=np.array([self.plot.left, self.plot.bottom, 0.0]),
            end=np.array([self.plot.left, self.plot.top, 0.0]),
            color=color,
            stroke_width=_AXIS_STROKE_WIDTH,
        )
        self.add(x_axis, y_axis)

    def _build_y_ticks(self, target_count: int) -> None:
        ticks = nice_ticks(self.y_min, self.y_max, target_count)
        # Track leftmost x of the y-tick label band so the y-axis title can
        # be placed with a clean buff to its left (instead of pinned to bbox).
        self._y_tick_label_left = self.plot.left - _TICK_LENGTH - _TICK_LABEL_BUFF
        for v in ticks:
            y = self.value_to_y(v)
            mark = Line(
                start=np.array([self.plot.left - _TICK_LENGTH, y, 0.0]),
                end=np.array([self.plot.left, y, 0.0]),
                color=UI["border"],
                stroke_width=_AXIS_STROKE_WIDTH,
            )
            label = Text(
                format_value(v, self._y_format, **self._y_format_opts),
                font=FONTS["primary"],
                font_size=self._tick_font_size(),
                color=UI["text_secondary"],
            )
            label.move_to(np.array([
                self.plot.left - _TICK_LENGTH - _TICK_LABEL_BUFF - label.width / 2,
                y,
                0.0,
            ]))
            label_left = label.get_left()[0]
            if label_left < self._y_tick_label_left:
                self._y_tick_label_left = label_left
            self.add(mark, label)

    def _build_x_labels(self, target_count: int) -> None:
        # Track the lowest y of the x-tick label band so the x-axis title
        # can be placed below it with a clean buff (instead of pinned to bbox).
        self._x_tick_label_bottom = self.plot.bottom - _TICK_LABEL_BUFF
        if self._categorical:
            for i, name in enumerate(self.x_categories):
                x = self.category_to_x(i)
                label = Text(
                    name,
                    font=FONTS["primary"],
                    font_size=self._tick_font_size(),
                    color=UI["text_secondary"],
                )
                label.move_to(np.array([
                    x,
                    self.plot.bottom - _TICK_LABEL_BUFF - label.height / 2,
                    0.0,
                ]))
                lbl_bottom = label.get_bottom()[1]
                if lbl_bottom < self._x_tick_label_bottom:
                    self._x_tick_label_bottom = lbl_bottom
                self.add(label)
            return

        ticks = nice_ticks(self.x_min, self.x_max, target_count)
        for v in ticks:
            x = self.value_to_x(v)
            mark = Line(
                start=np.array([x, self.plot.bottom - _TICK_LENGTH, 0.0]),
                end=np.array([x, self.plot.bottom, 0.0]),
                color=UI["border"],
                stroke_width=_AXIS_STROKE_WIDTH,
            )
            label = Text(
                format_value(v, self._x_format, **self._x_format_opts),
                font=FONTS["primary"],
                font_size=self._tick_font_size(),
                color=UI["text_secondary"],
            )
            label.move_to(np.array([
                x,
                self.plot.bottom - _TICK_LENGTH - _TICK_LABEL_BUFF - label.height / 2,
                0.0,
            ]))
            lbl_bottom = label.get_bottom()[1]
            if lbl_bottom < self._x_tick_label_bottom:
                self._x_tick_label_bottom = lbl_bottom
            self.add(mark, label)

    def _build_y_title(self, text: str) -> None:
        title = Text(
            text,
            font=FONTS["primary"],
            font_size=self._title_font_size(),
            color=UI["text_primary"],
        )
        title.rotate(np.pi / 2)
        # Position the y-axis title to the LEFT of the y-tick label band
        # with a clear buff. Falls back to bbox-pinning if the title would
        # overflow past the bbox left edge.
        band_left = getattr(
            self, "_y_tick_label_left", self.plot.left - _TICK_LENGTH - _TICK_LABEL_BUFF
        )
        title_center_x = band_left - _AXIS_TITLE_BUFF - title.width / 2
        bbox_left_min = -self.plot.bbox_width / 2 + 0.02 + title.width / 2
        title_center_x = max(title_center_x, bbox_left_min)
        title.move_to(np.array([
            title_center_x,
            (self.plot.bottom + self.plot.top) / 2,
            0.0,
        ]))
        self.add(title)

    def _build_x_title(self, text: str) -> None:
        title = Text(
            text,
            font=FONTS["primary"],
            font_size=self._title_font_size(),
            color=UI["text_primary"],
        )
        # Position the x-axis title BELOW the x-tick label band with a clear
        # buff. Falls back to bbox-pinning if the title would overflow past
        # the bbox bottom edge.
        band_bottom = getattr(
            self, "_x_tick_label_bottom", self.plot.bottom - _TICK_LABEL_BUFF
        )
        title_center_y = band_bottom - _AXIS_TITLE_BUFF - title.height / 2
        bbox_bottom_min = -self.plot.bbox_height / 2 + 0.02 + title.height / 2
        title_center_y = max(title_center_y, bbox_bottom_min)
        title.move_to(np.array([
            (self.plot.left + self.plot.right) / 2,
            title_center_y,
            0.0,
        ]))
        self.add(title)

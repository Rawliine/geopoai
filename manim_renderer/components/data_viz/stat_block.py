"""StatBlock — big number with label, optional unit, trend, and sparkline.

The "first data viz" component. Used in nearly every video to anchor a
narrative beat to a quantitative fact. Designed so an LLM can produce a
high-impact stat panel from a few JSON params:

```json
{
  "id": "stat-1", "value": 42.5,
  "label": "Defection rate",
  "unit": "%",
  "value_format": "decimal",
  "decimals": 1,
  "color": "actor_a",
  "trend": { "delta": 12.3, "direction": "up" },
  "sparkline": [10, 12, 9, 15, 18, 22, 25],
  "size": "medium",
  "timing": "normal",
  "effect": "count-up"
}
```

`set_value(v)` is implemented directly on the class — required by
`CountUpAnimation`. The base class's `_class_defines` check guards against
relying on Manim's synthesized setter.

Custom anchors:
  * `value` — center of the value text
  * `label` — center of the label text
  * `unit`  — center of the unit suffix (raises if no unit)
  * `trend` — center of the trend indicator (raises if no trend)
  * Standard 9 inherited from `BaseComponent`

Effects:
  * fade-in (default) — inherited
  * count-up — bespoke, animates value from 0 (or start_value) to target
  * grow-up / grow-down / slide-* — inherited
"""

from __future__ import annotations

from typing import Any

import numpy as np
from manim import Arrow, FadeIn, Text, UP, DOWN, ORIGIN

from manim_renderer.components.base import BaseComponent
from manim_renderer.components.data_viz._sparkline import Sparkline
from manim_renderer.components.data_viz._value_format import (
    VALUE_FORMATS,
    format_value,
)
from manim_renderer.effects._animations import CountUpAnimation
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


# Combined palette lookup — maps any palette key to its hex.
_PALETTE: dict[str, str] = {**ACTORS, **SEMANTIC, **UI}


def _color(key: str | None, default_key: str = "text_accent") -> str:
    """Resolve a palette key to a hex string. Hex codes are not allowed."""
    if key is None:
        return _PALETTE[default_key]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


# Trend direction → arrow direction + default semantic color.
_TREND_DIRECTIONS = {
    "up":   (UP,   "positive"),
    "down": (DOWN, "negative"),
    "flat": (None, "neutral"),
}


class StatBlock(BaseComponent):
    """Big number + label, with optional unit, trend, and inline sparkline."""

    # --- params parsing ------------------------------------------------------

    def build(self) -> None:
        p = self.params

        # Required
        if "value" not in p:
            raise ValueError("StatBlock requires params.value")
        if "label" not in p:
            raise ValueError("StatBlock requires params.label")

        self._value = float(p["value"])
        self._label_text = str(p["label"])

        # Optional with defaults
        self._unit = p.get("unit")
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

        self._color_key = p.get("color")  # palette key or None
        self._color_hex = _color(self._color_key, default_key="text_accent")

        self._size_role = p.get("size", "medium")  # for typography scaling

        # Build subcomponents in a deterministic stack order.
        self._build_value()
        self._build_label()
        if self._unit is not None:
            self._build_unit()
        if "trend" in p:
            self._build_trend(p["trend"])
        if "sparkline" in p:
            self._build_sparkline(p["sparkline"])

        self._lay_out()

        # Allow effects subsystem to find the value mobject.
        # CountUpAnimation will call self.set_value(...) which updates _value_mob.
        self.value_mobject = self  # set_value is on self, not on a child

    # --- subcomponent constructors -------------------------------------------

    def _value_font_size(self) -> int:
        # Title-class font for the big number; scaled per format.
        base = FONT_SCALE[self.format]["title"]
        # Rough role scaling so "small" stat is genuinely small.
        scale = {"small": 0.65, "medium": 1.0, "large": 1.3}.get(self._size_role, 1.0)
        return int(base * scale)

    def _label_font_size(self) -> int:
        base = FONT_SCALE[self.format]["label"]
        scale = {"small": 0.85, "medium": 1.0, "large": 1.15}.get(self._size_role, 1.0)
        return int(base * scale)

    def _build_value(self) -> None:
        self._value_mob = self._render_value_text(self._value)
        self.add(self._value_mob)

    def _render_value_text(self, value: float) -> Text:
        """Build the Text mobject for the number at a given value. Used by both
        initial build() and CountUpAnimation's per-frame replacement."""
        text = format_value(value, self._value_format, **self._format_opts)
        return Text(
            text,
            font=FONTS["primary"],
            font_size=self._value_font_size(),
            color=self._color_hex,
            weight="BOLD",
        )

    def _build_label(self) -> None:
        self._label_mob = Text(
            self._label_text,
            font=FONTS["primary"],
            font_size=self._label_font_size(),
            color=_color("text_secondary"),
        )
        self.add(self._label_mob)

    def _build_unit(self) -> None:
        # Smaller, dimmer suffix shown next to the value.
        self._unit_mob = Text(
            self._unit,
            font=FONTS["primary"],
            font_size=int(self._value_font_size() * 0.55),
            color=_color("text_secondary"),
        )
        self.add(self._unit_mob)

    def _build_trend(self, trend: dict) -> None:
        direction = trend.get("direction", "flat")
        if direction not in _TREND_DIRECTIONS:
            raise ValueError(
                f"trend.direction must be one of {sorted(_TREND_DIRECTIONS)}; "
                f"got {direction!r}"
            )
        delta = trend.get("delta")
        if delta is None:
            raise ValueError("trend requires a numeric `delta`")

        arrow_dir, default_color = _TREND_DIRECTIONS[direction]
        trend_color = _color(trend.get("color"), default_key=default_color)

        delta_text = format_value(
            float(delta),
            "signed",
            decimals=trend.get("decimals", 1),
        )
        if trend.get("unit"):
            delta_text += trend["unit"]

        delta_label = Text(
            delta_text,
            font=FONTS["primary"],
            font_size=int(self._label_font_size() * 1.05),
            color=trend_color,
            weight="BOLD",
        )

        if arrow_dir is not None:
            arrow = Arrow(
                start=ORIGIN,
                end=arrow_dir * 0.35,
                color=trend_color,
                stroke_width=4,
                buff=0,
                max_tip_length_to_length_ratio=0.4,
            )
            from manim import VGroup
            self._trend_mob = VGroup(arrow, delta_label).arrange(buff=0.12)
        else:
            self._trend_mob = delta_label

        self.add(self._trend_mob)

    def _build_sparkline(self, series: list) -> None:
        # Sparkline width scales with the size role; height stays small.
        spark_w = {"small": 1.2, "medium": 1.8, "large": 2.4}.get(
            self._size_role, 1.8
        )
        self._spark_mob = Sparkline(
            series,
            size=(spark_w, 0.5),
            line_color=self._color_hex,
        )
        self.add(self._spark_mob)

    # --- layout --------------------------------------------------------------

    def _lay_out(self) -> None:
        """Arrange children: value (big), unit (smaller, right of value),
        trend (right of value+unit, baseline-aligned), sparkline (below value
        row), label (bottom). Vertical-format scenes use the same stacking
        because the StatBlock itself is internally compact — its enclosing
        slot/anchor handles the page-level layout."""
        from manim import VGroup

        # Top row: value + unit on the same baseline; align unit's bottom to
        # roughly the value's lower-third for that classic "$1.2K" feel.
        if hasattr(self, "_unit_mob"):
            self._unit_mob.next_to(self._value_mob, RIGHT_OF_BASELINE := np.array([1, 0, 0]), buff=0.08)
            # nudge unit down so it sits on the baseline of the value
            target_y = self._value_mob.get_bottom()[1] + (self._value_mob.height * 0.18)
            self._unit_mob.move_to(np.array([
                self._unit_mob.get_center()[0],
                target_y + self._unit_mob.height / 2,
                0.0,
            ]))

        # Trend goes right of value (or value+unit), top-aligned.
        if hasattr(self, "_trend_mob"):
            anchor_mob = getattr(self, "_unit_mob", self._value_mob)
            self._trend_mob.next_to(anchor_mob, np.array([1, 0, 0]), buff=0.25)
            target_y = self._value_mob.get_top()[1] - self._trend_mob.height / 2 - 0.05
            self._trend_mob.move_to(np.array([
                self._trend_mob.get_center()[0],
                target_y,
                0.0,
            ]))

        # Sparkline directly under the value.
        if hasattr(self, "_spark_mob"):
            self._spark_mob.next_to(
                self._value_mob, np.array([0, -1, 0]), buff=0.18
            )

        # Label always at the bottom of the block.
        bottom_anchor = (
            self._spark_mob if hasattr(self, "_spark_mob") else self._value_mob
        )
        self._label_mob.next_to(
            bottom_anchor, np.array([0, -1, 0]), buff=0.18
        )

        # Center the whole VGroup at origin (slot/anchor positioning happens later).
        self.move_to(ORIGIN)

    # --- count-up: required for CountUpAnimation -----------------------------

    def set_value(self, value: float) -> None:
        """Re-render the value text in place. Called by CountUpAnimation each
        frame; the text mobject is replaced and re-positioned identically.

        This MUST be defined directly on the class (not via Manim's synthesized
        setter) — see `effects/_animations.py:_class_defines`.
        """
        new_mob = self._render_value_text(value)
        # Preserve position: align new mob to old mob's center before swap.
        new_mob.move_to(self._value_mob.get_center())
        self.remove(self._value_mob)
        self._value_mob = new_mob
        self.add(self._value_mob)

    # --- bespoke entrance ----------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "count-up":
            run_time = TIMING[timing]
            start_value = float(extra.get("start_value", 0))
            target_value = float(extra.get("target_value", self._value))
            # Snap to start so the FadeIn-into-counter looks right.
            self.set_value(start_value)
            # Fade in label/unit/sparkline (everything except the value)
            # in parallel with the count-up to give the whole block a unified
            # entrance. Use group with same run_time.
            from manim import AnimationGroup
            non_value_children = [
                child for child in self.submobjects if child is not self._value_mob
            ]
            count = CountUpAnimation(
                self,
                start_value=start_value,
                target_value=target_value,
                run_time=run_time,
            )
            if not non_value_children:
                return count
            from manim import VGroup
            group_mob = VGroup(*non_value_children)
            return AnimationGroup(count, FadeIn(group_mob, run_time=run_time))
        return super().entrance(effect, timing, **extra)

    # --- custom anchor methods -----------------------------------------------

    def _get_anchor_value(self) -> np.ndarray:
        return self._value_mob.get_center()

    def _get_anchor_label(self) -> np.ndarray:
        return self._label_mob.get_center()

    def _get_anchor_unit(self) -> np.ndarray:
        if not hasattr(self, "_unit_mob"):
            raise KeyError("StatBlock has no `unit` anchor — params.unit was not set")
        return self._unit_mob.get_center()

    def _get_anchor_trend(self) -> np.ndarray:
        if not hasattr(self, "_trend_mob"):
            raise KeyError("StatBlock has no `trend` anchor — params.trend was not set")
        return self._trend_mob.get_center()

    def _get_anchor_sparkline(self) -> np.ndarray:
        if not hasattr(self, "_spark_mob"):
            raise KeyError(
                "StatBlock has no `sparkline` anchor — params.sparkline was not set"
            )
        return self._spark_mob.get_center()

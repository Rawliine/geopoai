"""Timeline — single component with format-aware orientation.

Per recap.md §7 (LOCKED): one component, format flag drives behavior. No
`HorizontalTimeline` / `VerticalTimeline` twins.

  * horizontal format → axis runs left-to-right, dots evenly spaced along x,
    event labels alternate above/below the axis to avoid overlap.
  * vertical format   → axis runs top-to-bottom, dots evenly spaced along y,
    event labels to the right of dots, at_label (date) to the left.

Vertical depth cap: events past `max_visible` (default 8) are not rendered.
Document this in handoff; future improvement is an `…` ellipsis dot at the cap.

Custom anchors:
  * `event:<i_or_id>`       — that event's dot center
  * `event:<i_or_id>.label` — that event's label text center

```json
{
  "action": "showTimeline",
  "params": {
    "id": "tl",
    "events": [
      { "id": "wwii", "at_label": "1939", "label": "WWII begins" },
      { "id": "vj",   "at_label": "1945", "label": "VJ Day", "color": "highlight" }
    ],
    "size": "medium",
    "timing": "normal",
    "effect": "level-by-level"
  }
}
```
"""

from __future__ import annotations

import numpy as np
from manim import (
    Dot,
    FadeIn,
    LaggedStart,
    Line,
    ORIGIN,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.resolvers.size import resolve_size
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import STAGGER, TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


_PALETTE: dict[str, str] = {**ACTORS, **SEMANTIC, **UI}


_AXIS_STROKE = 2.0
_DOT_RADIUS = 0.10
_LABEL_BUFF = 0.18
_DATE_BUFF = 0.10
_VERTICAL_MAX_VISIBLE_DEFAULT = 8


def _resolve_color(key: str | None, fallback: str = "text_accent") -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


class Timeline(BaseComponent):
    """Format-aware single-axis timeline."""

    def build(self) -> None:
        p = self.params

        events = p.get("events")
        if not events or not isinstance(events, list):
            raise ValueError("Timeline requires non-empty params.events list")

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="default")

        max_visible = int(p.get("max_visible", _VERTICAL_MAX_VISIBLE_DEFAULT))
        # In horizontal we honor all events; in vertical we cap to prevent
        # off-frame events from being drawn out of view.
        if self.format == "vertical" and len(events) > max_visible:
            events = events[:max_visible]

        self._event_ids: list[str | None] = [e.get("id") for e in events]
        self._event_labels: list[str] = [str(e.get("label", "")) for e in events]
        self._at_labels: list[str | None] = [e.get("at_label") for e in events]
        self._event_colors: list[str] = [
            _resolve_color(e.get("color")) for e in events
        ]

        if self.format == "horizontal":
            self._build_horizontal(width, height)
        else:
            self._build_vertical(width, height)

        self.move_to(ORIGIN)

    # --- format-specific builders -------------------------------------------

    def _build_horizontal(self, width: float, height: float) -> None:
        # Axis line spans most of the width, centered vertically.
        n = len(self._event_ids)
        margin = width * 0.06
        x_left = -width / 2 + margin
        x_right = width / 2 - margin

        axis = Line(
            start=np.array([x_left, 0.0, 0.0]),
            end=np.array([x_right, 0.0, 0.0]),
            color=UI["border"],
            stroke_width=_AXIS_STROKE,
        )
        self.add(axis)
        self._axis = axis

        # Evenly spaced dot x-positions; for n=1, place at center.
        if n == 1:
            xs = [0.0]
        else:
            xs = list(np.linspace(x_left, x_right, n))

        self._dots: list[Dot] = []
        self._label_mobs: list[Text] = []
        self._date_mobs: list[Text | None] = []
        label_size = int(FONT_SCALE[self.format]["caption"] * 0.9)
        date_size = int(FONT_SCALE[self.format]["caption"] * 0.78)

        for i, (x, color) in enumerate(zip(xs, self._event_colors)):
            dot = Dot(np.array([x, 0.0, 0.0]), radius=_DOT_RADIUS, color=color)
            self.add(dot)
            self._dots.append(dot)

            # Alternate label above/below axis (even indices above).
            label_y_dir = 1 if i % 2 == 0 else -1
            label_mob = Text(
                self._event_labels[i],
                font=FONTS["primary"],
                font_size=label_size,
                color=UI["text_primary"],
            )
            label_y = (
                label_y_dir
                * (_DOT_RADIUS + _LABEL_BUFF + label_mob.height / 2)
            )
            label_mob.move_to(np.array([x, label_y, 0.0]))
            self.add(label_mob)
            self._label_mobs.append(label_mob)

            if self._at_labels[i]:
                date_mob = Text(
                    self._at_labels[i],
                    font=FONTS["primary"],
                    font_size=date_size,
                    color=UI["text_secondary"],
                )
                # Dates always on the opposite side of the label.
                date_y_dir = -label_y_dir
                date_y = (
                    date_y_dir
                    * (_DOT_RADIUS + _DATE_BUFF + date_mob.height / 2)
                )
                date_mob.move_to(np.array([x, date_y, 0.0]))
                self.add(date_mob)
                self._date_mobs.append(date_mob)
            else:
                self._date_mobs.append(None)

    def _build_vertical(self, width: float, height: float) -> None:
        n = len(self._event_ids)
        margin = height * 0.06
        y_top = height / 2 - margin
        y_bottom = -height / 2 + margin

        # Center axis horizontally — dots on axis, labels to the right, dates to left.
        axis = Line(
            start=np.array([0.0, y_top, 0.0]),
            end=np.array([0.0, y_bottom, 0.0]),
            color=UI["border"],
            stroke_width=_AXIS_STROKE,
        )
        self.add(axis)
        self._axis = axis

        if n == 1:
            ys = [0.0]
        else:
            ys = list(np.linspace(y_top, y_bottom, n))

        self._dots = []
        self._label_mobs = []
        self._date_mobs = []
        label_size = int(FONT_SCALE[self.format]["caption"] * 0.9)
        date_size = int(FONT_SCALE[self.format]["caption"] * 0.78)

        for i, (y, color) in enumerate(zip(ys, self._event_colors)):
            dot = Dot(np.array([0.0, y, 0.0]), radius=_DOT_RADIUS, color=color)
            self.add(dot)
            self._dots.append(dot)

            label_mob = Text(
                self._event_labels[i],
                font=FONTS["primary"],
                font_size=label_size,
                color=UI["text_primary"],
            )
            label_x = _DOT_RADIUS + _LABEL_BUFF + label_mob.width / 2
            label_mob.move_to(np.array([label_x, y, 0.0]))
            self.add(label_mob)
            self._label_mobs.append(label_mob)

            if self._at_labels[i]:
                date_mob = Text(
                    self._at_labels[i],
                    font=FONTS["primary"],
                    font_size=date_size,
                    color=UI["text_secondary"],
                )
                date_x = -(_DOT_RADIUS + _DATE_BUFF + date_mob.width / 2)
                date_mob.move_to(np.array([date_x, y, 0.0]))
                self.add(date_mob)
                self._date_mobs.append(date_mob)
            else:
                self._date_mobs.append(None)

    # --- child id registration ----------------------------------------------

    def extra_id_registrations(self) -> dict:
        """Expose each named event's dot as a top-level id, so JSON authors
        can anchor against `below:wwii` directly. Events without an `id` are
        not exposed.

        Must stay in sync with `schema/validator.py:_ids_from_timeline`.
        """
        return {
            eid: dot
            for eid, dot in zip(self._event_ids, self._dots)
            if eid
        }

    # --- bespoke entrance ---------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "level-by-level":
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])

            # Axis fades in first (fast), then each event group (dot+label+date)
            # reveals in sequence.
            axis_anim = FadeIn(self._axis, run_time=TIMING["fast"])
            event_groups = []
            for dot, label, date in zip(self._dots, self._label_mobs, self._date_mobs):
                parts = [dot, label]
                if date is not None:
                    parts.append(date)
                event_groups.append(VGroup(*parts))
            lagged = LaggedStart(
                *(FadeIn(g) for g in event_groups),
                lag_ratio=lag,
                run_time=run_time,
            )
            from manim import AnimationGroup, Succession
            return Succession(axis_anim, lagged)
        return super().entrance(effect, timing, **extra)

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_event(self, arg: str) -> np.ndarray:
        """`event:<i_or_id>` -> dot center. `event:<i_or_id>.label` -> label center."""
        ident, sep, suffix = arg.partition(".")
        idx = self._lookup_event_index(ident)
        if not sep:
            return self._dots[idx].get_center()
        if suffix == "label":
            return self._label_mobs[idx].get_center()
        if suffix == "date":
            if self._date_mobs[idx] is None:
                raise KeyError(
                    f"Timeline event:{ident}.date — no at_label on this event"
                )
            return self._date_mobs[idx].get_center()
        raise KeyError(
            f"Timeline event suffix must be 'label' or 'date'; got {suffix!r}"
        )

    def _lookup_event_index(self, ident: str) -> int:
        if ident.isdigit():
            i = int(ident)
            if not 0 <= i < len(self._dots):
                raise KeyError(
                    f"Timeline `event:{ident}` out of range [0, {len(self._dots)})"
                )
            return i
        if ident in self._event_ids:
            return self._event_ids.index(ident)
        raise KeyError(
            f"Timeline has no event with id={ident!r}; "
            f"available: indices 0..{len(self._dots)-1}, "
            f"named ids: {[e for e in self._event_ids if e]}"
        )

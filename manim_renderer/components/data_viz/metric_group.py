"""MetricGroup — bundle of StatBlocks with shared styling and orientation.

Wraps N StatBlock children under one id, arranged in a row (horizontal format)
or column (vertical format). Children inherit shared styling (size, color
scheme) from group-level params; per-stat overrides win.

Why this exists vs. just using the `trio` layout:
  * Single id for the whole bundle simplifies anchor targeting (one callout
    can point at the group rather than picking one stat).
  * Shared `value_format` and `color_scheme` keeps the stack visually uniform.
  * `entrance="staggered"` reveals stats sequentially with a `LaggedStart`,
    which the trio layout can't coordinate from JSON alone.
  * Per-child anchors are exposed as `stat:0`, `stat:1`, ... or `stat:<id>`
    when a stat declared its own id.

Custom anchors:
  * `stat:<index_or_id>` → that stat's center
  * Standard 9 inherited from BaseComponent
"""

from __future__ import annotations

from typing import Any

import numpy as np
from manim import AnimationGroup, FadeIn, LaggedStart, ORIGIN

from manim_renderer.components.base import BaseComponent
from manim_renderer.components.data_viz.stat_block import StatBlock
from manim_renderer.theme.timing import STAGGER, TIMING


# Color rotation when no explicit per-stat color is set and a color_scheme is
# requested. "actors" cycles actor_a/b/c/d/e; "semantic" cycles positive/
# neutral/negative; "accent" uses highlight for all.
_COLOR_SCHEMES: dict[str, list[str]] = {
    "actors":   ["actor_a", "actor_b", "actor_c", "actor_d", "actor_e"],
    "semantic": ["positive", "neutral", "negative"],
    "accent":   ["highlight"],
}


class MetricGroup(BaseComponent):
    """Row (horizontal) / column (vertical) of StatBlocks under one id."""

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        """Sum or max of child StatBlock dimensions along the orientation axis.

        Row    → max(child widths), sum(child heights) is wrong — use max h, sum w.
        Column → max(child widths), sum(child heights).

        Shared style inheritance is honored so children see the same `size`
        param the runtime uses.
        """
        stats = params.get("stats") or []
        if not stats:
            return (0.0, 0.0)

        orientation = params.get(
            "orientation",
            "row" if format == "horizontal" else "column",
        )
        spacing = float(params.get("spacing", 0.6))

        shared_size = params.get("size", "medium")
        shared_value_format = params.get("value_format")

        widths: list[float] = []
        heights: list[float] = []
        for stat_params in stats:
            child = dict(stat_params)
            child.setdefault("size", shared_size)
            if shared_value_format is not None:
                child.setdefault("value_format", shared_value_format)
            w, h = StatBlock.measure(child, format)
            widths.append(w)
            heights.append(h)

        n = len(stats)
        if orientation == "row":
            total_w = sum(widths) + spacing * max(0, n - 1)
            total_h = max(heights)
        else:
            total_w = max(widths)
            total_h = sum(heights) + spacing * max(0, n - 1)
        return (total_w, total_h)

    def build(self) -> None:
        p = self.params

        if "stats" not in p or not isinstance(p["stats"], list) or not p["stats"]:
            raise ValueError("MetricGroup requires non-empty params.stats list")

        self._orientation = p.get(
            "orientation",
            "row" if self.format == "horizontal" else "column",
        )
        if self._orientation not in ("row", "column"):
            raise ValueError(
                f"MetricGroup orientation must be 'row' or 'column'; "
                f"got {self._orientation!r}"
            )

        self._buff = float(p.get("spacing", 0.6))

        # Shared style inheritance
        shared = {
            "size": p.get("size", "medium"),
            "value_format": p.get("value_format"),
            "color": None,  # set per child via color_scheme rotation
        }
        scheme = p.get("color_scheme")
        scheme_colors = _COLOR_SCHEMES.get(scheme, []) if scheme else []

        # Build children
        self._stats: list[StatBlock] = []
        self._stat_ids: list[str | None] = []
        for i, stat_params in enumerate(p["stats"]):
            child_params = self._merge_child_params(
                stat_params, shared, scheme_colors, i
            )
            stat = StatBlock(child_params, format=self.format)
            self._stats.append(stat)
            self._stat_ids.append(stat_params.get("id"))
            self.add(stat)

        self._lay_out()

    # --- params merge --------------------------------------------------------

    @staticmethod
    def _merge_child_params(
        stat_params: dict,
        shared: dict,
        scheme_colors: list[str],
        index: int,
    ) -> dict:
        """Apply group-level defaults to a child stat's params. Per-stat
        values always win. Group's `id` is NOT inherited (children would
        collide); children get their own optional ids."""
        merged = dict(stat_params)
        for key, val in shared.items():
            if val is None:
                continue
            merged.setdefault(key, val)
        if "color" not in merged and scheme_colors:
            merged["color"] = scheme_colors[index % len(scheme_colors)]
        return merged

    # --- layout --------------------------------------------------------------

    def _lay_out(self) -> None:
        if not self._stats:
            return

        # Use the first stat's center as anchor; arrange the rest along the
        # appropriate axis with `_buff` between them.
        if self._orientation == "row":
            direction = np.array([1.0, 0.0, 0.0])
        else:
            direction = np.array([0.0, -1.0, 0.0])

        for prev, curr in zip(self._stats, self._stats[1:]):
            curr.next_to(prev, direction, buff=self._buff)

        # Center the whole group at origin.
        self.move_to(ORIGIN)

    # --- child id registration -----------------------------------------------

    def extra_id_registrations(self) -> dict:
        """Expose each named child stat as a top-level id, so JSON authors can
        anchor against `below:k-defect` etc. directly. Stats without an `id`
        are not exposed."""
        return {
            sid: stat
            for sid, stat in zip(self._stat_ids, self._stats)
            if sid
        }

    # --- bespoke entrance ----------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "staggered":
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])
            child_anims = [
                stat.entrance(extra.get("child_effect", "fade-in"), timing)
                for stat in self._stats
            ]
            return LaggedStart(*child_anims, lag_ratio=lag, run_time=run_time)
        return super().entrance(effect, timing, **extra)

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_stat(self, arg: str) -> np.ndarray:
        """`stat:<index_or_id>` → that stat's center.

        Numeric arg is interpreted as a 0-based index. Otherwise looked up
        against per-stat ids (the optional `id` on each stat in `params.stats`).
        """
        if arg.isdigit():
            idx = int(arg)
            if not 0 <= idx < len(self._stats):
                raise KeyError(
                    f"MetricGroup `stat:{arg}` out of range "
                    f"[0, {len(self._stats)})"
                )
            return self._stats[idx].get_center()
        if arg in self._stat_ids:
            return self._stats[self._stat_ids.index(arg)].get_center()
        raise KeyError(
            f"MetricGroup has no stat with id={arg!r}; "
            f"available indices: 0..{len(self._stats)-1}, "
            f"named ids: {[i for i in self._stat_ids if i]}"
        )

"""PayoffMatrix — N×N game-theory normal-form matrix.

The signature game-theory component. Cells display payoff pairs `(a, b)`
colored by player (row player's payoff in their color, col player's in
theirs). Row + column strategy labels border the grid; player names sit above
and to the left of the strategy labels.

This component is the canonical target for the three Phase 1 mutation
actions: `highlightCell`, `crossOut`, `bestResponseArrow` — they read its
custom anchors to place overlays.

Custom anchors:
  * `cell:i,j` — center of cell (row i, col j). 0-based indices.
  * `row:i`    — left edge of row i (where the row strategy label sits)
  * `col:j`    — top edge of column j (where the col strategy label sits)
  * Standard 9 inherited.

Defaults: 2×2 Prisoner's Dilemma fits naturally. Larger matrices supported
up to 6×6 (schema-enforced).

```json
{
  "action": "showPayoffMatrix",
  "params": {
    "id": "pd",
    "players": [
      { "name": "P1", "color": "actor_a" },
      { "name": "P2", "color": "actor_b" }
    ],
    "strategies": [
      ["Cooperate", "Defect"],
      ["Cooperate", "Defect"]
    ],
    "cells": [
      [{ "a": 3, "b": 3 }, { "a": 0, "b": 5 }],
      [{ "a": 5, "b": 0 }, { "a": 1, "b": 1 }]
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
    AnimationGroup,
    FadeIn,
    LaggedStart,
    Line,
    ORIGIN,
    Rectangle,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.resolvers.size import resolve_size
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.spacing import spacing
from manim_renderer.theme.timing import STAGGER, TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


_PALETTE = {**ACTORS, **SEMANTIC, **UI}

_CELL_STROKE_WIDTH = 1.5
_GRID_STROKE_WIDTH = 1.0
_PAYOFF_BUFF = 0.10  # gap between the two payoff numbers in a cell


def _resolve_color(key: str | None, fallback: str = "text_primary") -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


class PayoffMatrix(BaseComponent):
    """N×N normal-form game matrix."""

    SIZE_KIND = "matrix"

    def build(self) -> None:
        p = self.params

        players = p.get("players")
        if not players or len(players) != 2:
            raise ValueError("PayoffMatrix requires exactly 2 players")
        strategies = p.get("strategies")
        if not strategies or len(strategies) != 2:
            raise ValueError("PayoffMatrix requires 2 strategy lists (row, col)")
        cells = p.get("cells")
        if not cells:
            raise ValueError("PayoffMatrix requires non-empty cells matrix")

        self._n_rows = len(strategies[0])
        self._n_cols = len(strategies[1])
        if self._n_rows < 2 or self._n_cols < 2:
            raise ValueError("PayoffMatrix must be at least 2×2")
        if len(cells) != self._n_rows or any(len(row) != self._n_cols for row in cells):
            raise ValueError(
                f"PayoffMatrix cells shape mismatch: expected "
                f"{self._n_rows}×{self._n_cols}"
            )

        self._row_player = players[0]
        self._col_player = players[1]
        self._row_color = _resolve_color(self._row_player.get("color"), "actor_a")
        self._col_color = _resolve_color(self._col_player.get("color"), "actor_b")
        self._row_strategies = list(strategies[0])
        self._col_strategies = list(strategies[1])
        self._cells_data = cells

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="matrix")

        # Carve geometry:
        #   left strip (row labels), top strip (col labels), corner (player names).
        # The grid fills the remaining lower-right rectangle.
        label_strip = min(width, height) * 0.15
        grid_left = -width / 2 + label_strip
        grid_right = width / 2
        grid_top = height / 2 - label_strip
        grid_bottom = -height / 2

        grid_w = grid_right - grid_left
        grid_h = grid_top - grid_bottom
        self._cell_w = grid_w / self._n_cols
        self._cell_h = grid_h / self._n_rows

        # Cell rects + payoff texts.
        self._cell_rects: dict[tuple[int, int], Rectangle] = {}
        self._cell_groups: dict[tuple[int, int], VGroup] = {}
        payoff_font_size = int(FONT_SCALE[self.format]["body"] * 0.65)

        for i in range(self._n_rows):
            for j in range(self._n_cols):
                cx = grid_left + (j + 0.5) * self._cell_w
                cy = grid_top - (i + 0.5) * self._cell_h
                rect = Rectangle(
                    width=self._cell_w,
                    height=self._cell_h,
                    color=UI["border"],
                    stroke_width=_CELL_STROKE_WIDTH,
                    fill_color=UI["surface"],
                    fill_opacity=0.15,
                )
                rect.move_to(np.array([cx, cy, 0.0]))
                self._cell_rects[(i, j)] = rect

                cell_payoffs = cells[i][j]
                a_mob = Text(
                    str(cell_payoffs.get("a", "")),
                    font=FONTS["primary"],
                    font_size=payoff_font_size,
                    color=self._row_color,
                    weight="BOLD",
                )
                b_mob = Text(
                    str(cell_payoffs.get("b", "")),
                    font=FONTS["primary"],
                    font_size=payoff_font_size,
                    color=self._col_color,
                    weight="BOLD",
                )
                sep_mob = Text(
                    ",",
                    font=FONTS["primary"],
                    font_size=payoff_font_size,
                    color=UI["text_secondary"],
                )
                pair = VGroup(a_mob, sep_mob, b_mob).arrange(
                    np.array([1, 0, 0]), buff=_PAYOFF_BUFF / 2,
                )
                pair.move_to(np.array([cx, cy, 0.0]))
                cell_group = VGroup(rect, pair)
                self._cell_groups[(i, j)] = cell_group
                self.add(cell_group)

        # Strategy labels: row labels (left strip), col labels (top strip).
        # Gap from the grid edge is token-derived (theme.spacing), not a magic
        # number, so it tracks the brand type scale per format.
        label_font_size = int(FONT_SCALE[self.format]["caption"] * 0.95)
        label_gap = spacing("label_gap", self.format)
        self._row_labels: list[Text] = []
        self._col_labels: list[Text] = []
        for i, name in enumerate(self._row_strategies):
            cy = grid_top - (i + 0.5) * self._cell_h
            label = Text(
                name,
                font=FONTS["primary"],
                font_size=label_font_size,
                color=UI["text_primary"],
            )
            label.move_to(np.array([
                grid_left - label.width / 2 - label_gap,
                cy,
                0.0,
            ]))
            self._row_labels.append(label)
            self.add(label)
        for j, name in enumerate(self._col_strategies):
            cx = grid_left + (j + 0.5) * self._cell_w
            label = Text(
                name,
                font=FONTS["primary"],
                font_size=label_font_size,
                color=UI["text_primary"],
            )
            label.move_to(np.array([
                cx,
                grid_top + label.height / 2 + label_gap,
                0.0,
            ]))
            self._col_labels.append(label)
            self.add(label)

        # Player names: outboard of their strategy-label band. Positioned
        # RELATIVE to the actual band edge plus a token gap so the name never
        # crowds the strategy labels — the previous fixed `label_strip * 0.7`
        # offset let long strategy labels overlap the player name (the col name
        # touched / overlapped the strategy row in vertical format).
        player_font_size = int(FONT_SCALE[self.format]["caption"] * 1.0)
        title_gap = spacing("axis_title_gap", self.format)
        row_band_left = min(lbl.get_left()[0] for lbl in self._row_labels)
        col_band_top = max(lbl.get_top()[1] for lbl in self._col_labels)

        row_player_label = Text(
            self._row_player["name"],
            font=FONTS["primary"],
            font_size=player_font_size,
            color=self._row_color,
            weight="BOLD",
        )
        row_player_label.rotate(np.pi / 2)
        row_player_label.move_to(np.array([
            row_band_left - title_gap - row_player_label.width / 2,
            (grid_top + grid_bottom) / 2,
            0.0,
        ]))
        self.add(row_player_label)
        self._row_player_label = row_player_label

        col_player_label = Text(
            self._col_player["name"],
            font=FONTS["primary"],
            font_size=player_font_size,
            color=self._col_color,
            weight="BOLD",
        )
        col_player_label.move_to(np.array([
            (grid_left + grid_right) / 2,
            col_band_top + title_gap + col_player_label.height / 2,
            0.0,
        ]))
        self.add(col_player_label)
        self._col_player_label = col_player_label

        # Store the grid bounds so mutation actions can compute row/col bands.
        self._grid_bounds = (grid_left, grid_right, grid_top, grid_bottom)

        self.move_to(ORIGIN)

        # Snapshot the overall width AND each cell's center relative to
        # the matrix center. `mob.copy()` doesn't update custom dict refs
        # to point at copied submobjects, so `self._cell_rects` lookups
        # go stale on a scaled copy. Plain numpy arrays and floats survive
        # the copy by value, so we use them to derive cell geometry from
        # the live matrix center + scale factor.
        self._build_width = float(self.width) if self.width else 1.0
        center = self.get_center()
        self._cell_offsets: dict[tuple[int, int], np.ndarray] = {
            key: np.asarray(rect.get_center() - center, dtype=float)
            for key, rect in self._cell_rects.items()
        }
        self._row_label_offsets: list[np.ndarray] = [
            np.asarray(lbl.get_center() - center, dtype=float)
            for lbl in self._row_labels
        ]
        self._col_label_offsets: list[np.ndarray] = [
            np.asarray(lbl.get_center() - center, dtype=float)
            for lbl in self._col_labels
        ]

    # --- bespoke entrance ---------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "level-by-level":
            # Row-by-row reveal. Labels appear first, then each row of cells.
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])

            label_group = VGroup(
                self._row_player_label,
                self._col_player_label,
                *self._row_labels,
                *self._col_labels,
            )
            labels_anim = FadeIn(label_group, run_time=TIMING["fast"])

            row_anims = []
            for i in range(self._n_rows):
                row_group = VGroup(*[self._cell_groups[(i, j)] for j in range(self._n_cols)])
                row_anims.append(FadeIn(row_group))

            from manim import Succession
            lagged = LaggedStart(*row_anims, lag_ratio=lag, run_time=run_time)
            return Succession(labels_anim, lagged)
        return super().entrance(effect, timing, **extra)

    # --- helpers (called by mutation actions) -------------------------------

    def cell_dims(self) -> tuple[float, float]:
        """(width, height) of a single cell. Reads the live overall width
        of the matrix against the build-time snapshot to derive the
        current scale factor — works whether this is the original mobject
        or a scaled `.copy()` that the restage walker passes as the
        synthetic host. `self._cell_rects` can't be trusted on a copy
        because Manim's deep-copy doesn't rewrite custom dict refs to
        point at the copied submobjects."""
        scale = self._live_scale_factor()
        return (self._cell_w * scale, self._cell_h * scale)

    def _live_scale_factor(self) -> float:
        build = getattr(self, "_build_width", 0.0)
        current = float(self.width) if self.width else 0.0
        if build <= 0 or current <= 0:
            return 1.0
        return current / build

    def row_player_color(self) -> str:
        return self._row_color

    def col_player_color(self) -> str:
        return self._col_color

    def n_rows(self) -> int:
        return self._n_rows

    def n_cols(self) -> int:
        return self._n_cols

    # --- custom anchors -----------------------------------------------------

    def _get_anchor_cell(self, arg: str) -> np.ndarray:
        """`cell:i,j` -> center of cell (row i, col j)."""
        try:
            i_str, j_str = arg.split(",")
            i, j = int(i_str), int(j_str)
        except (ValueError, TypeError):
            raise KeyError(
                f"PayoffMatrix cell anchor expects 'i,j' (two ints); got {arg!r}"
            )
        if not (0 <= i < self._n_rows and 0 <= j < self._n_cols):
            raise KeyError(
                f"PayoffMatrix cell ({i},{j}) out of bounds "
                f"({self._n_rows}×{self._n_cols})"
            )
        offsets = getattr(self, "_cell_offsets", None)
        if offsets is None:
            return self._cell_rects[(i, j)].get_center()
        return self.get_center() + offsets[(i, j)] * self._live_scale_factor()

    def _get_anchor_row(self, arg: str) -> np.ndarray:
        """`row:i` -> center of the row's left edge (where the row label sits)."""
        try:
            i = int(arg)
        except (ValueError, TypeError):
            raise KeyError(f"PayoffMatrix row anchor expects an int; got {arg!r}")
        if not 0 <= i < self._n_rows:
            raise KeyError(f"PayoffMatrix row {i} out of range [0, {self._n_rows})")
        offsets = getattr(self, "_row_label_offsets", None)
        if offsets is None:
            return self._row_labels[i].get_center()
        return self.get_center() + offsets[i] * self._live_scale_factor()

    def _get_anchor_col(self, arg: str) -> np.ndarray:
        """`col:j` -> center of the column's top edge (where the col label sits)."""
        try:
            j = int(arg)
        except (ValueError, TypeError):
            raise KeyError(f"PayoffMatrix col anchor expects an int; got {arg!r}")
        if not 0 <= j < self._n_cols:
            raise KeyError(f"PayoffMatrix col {j} out of range [0, {self._n_cols})")
        offsets = getattr(self, "_col_label_offsets", None)
        if offsets is None:
            return self._col_labels[j].get_center()
        return self.get_center() + offsets[j] * self._live_scale_factor()

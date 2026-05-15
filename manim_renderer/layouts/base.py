"""Layout primitives. A Layout is a set of named slots; each slot is a Rect
in Manim unit space (origin at frame center, y-up).

`FRAME_BOUNDS` is the renderable area per format — consumed by the validator's
overflow checks (`schema/_dry_run.py`) and by the future layout solver. Values
must match Manim's frame_width/frame_height for each format (set in
`pipeline/render_manim.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


FRAME_BOUNDS: dict[str, tuple[float, float]] = {
    "horizontal": (14.2, 8.0),
    "vertical":   (8.0, 14.2),
}


# Phase 2 / PR H — per-role linear scale applied by the default
# `BaseComponent.preferred_size`. Content-driven components override the
# whole method when linear scaling doesn't fit their content (text width
# floors, axis labels, etc.). `hidden` → (0, 0) so the solver allocates no
# space and the runner can drop the mobject from the live cast.
ROLE_SCALE: dict[str, float] = {
    "hero":       1.5,
    "primary":    1.0,
    "supporting": 0.7,
    "ambient":    0.4,
    "annotation": 1.0,
    "hidden":     0.0,
}


@dataclass(frozen=True)
class Rect:
    cx: float
    cy: float
    width: float
    height: float

    @property
    def center(self) -> np.ndarray:
        return np.array([self.cx, self.cy, 0.0])

    @property
    def size(self) -> tuple[float, float]:
        return (self.width, self.height)


@dataclass(frozen=True)
class CastMember:
    """One live entry in the scene's current cast.

    The scene runner builds this from `_id_to_mobject` + `_roles` +
    `_id_to_slot` whenever it calls `Layout.solve(cast)`. Fields are
    immutable per-pass so the solver can be cached safely.
    """
    id: str
    role: str
    preferred_size: tuple[float, float]
    slot: str | None = None


# Per-layout flex direction for the default solver. `split` lays its
# slot contents left-to-right within each slot; `stacked` top-to-bottom;
# trio horizontally; trio-stack vertically; the rest fall back to
# horizontal which is harmless for hero/title-body (single-member slots
# get the slot rect verbatim).
_LAYOUT_FLEX_DIRECTION: dict[str, str] = {
    "split":       "horizontal",
    "stacked":     "vertical",
    "trio":        "horizontal",
    "trio-stack":  "vertical",
    "data-left":   "vertical",
    "data-top":    "horizontal",
    "title-body":  "vertical",
    "hero":        "vertical",
}


@dataclass(frozen=True)
class Layout:
    name: str
    format: str  # "horizontal" | "vertical"
    slots: Dict[str, Rect]

    def slot(self, name: str) -> Rect:
        if name not in self.slots:
            raise KeyError(
                f"layout {self.name!r} ({self.format}) has no slot {name!r}; "
                f"available: {sorted(self.slots)}"
            )
        return self.slots[name]

    def has_slot(self, name: str) -> bool:
        return name in self.slots

    # --- Phase 2 / PR J — solver interface ----------------------------------

    def solve(self, cast: "list[CastMember]") -> dict[str, Rect]:
        """Allocate scene rects for the live cast.

        Default contract:
          * Each slot-bound member with no slot-mates gets the slot rect
            verbatim (backward compat — PD scenes render identically).
          * Multi-member slots run `flex_solve` within the slot rect along
            the layout's per-direction axis (see `_LAYOUT_FLEX_DIRECTION`).
          * Members without a slot (anchored callouts pre-PR L) are NOT
            placed by the solver — the runner keeps their static anchor.

        Subclasses may override for special semantics (e.g. `title-body`
        pinning the title strip and flexing only the body cast).
        """
        from manim_renderer.layouts._flex import flex_solve

        out: dict[str, Rect] = {}
        members_by_slot: dict[str, list[CastMember]] = {}
        for m in cast:
            if m.slot is not None and m.slot in self.slots:
                members_by_slot.setdefault(m.slot, []).append(m)

        direction = _LAYOUT_FLEX_DIRECTION.get(self.name, "horizontal")

        for slot_name, members in members_by_slot.items():
            slot_rect = self.slots[slot_name]
            visible = [m for m in members if m.role != "hidden"]
            if not visible:
                continue
            non_annotation = [m for m in visible if m.role != "annotation"]
            if len(visible) == 1 and len(non_annotation) == 1:
                # Backward compat: lone primary owns the slot rect.
                out[visible[0].id] = slot_rect
                continue
            allocs = flex_solve(
                [(m.id, m.role, m.preferred_size) for m in visible],
                container=slot_rect,
                direction=direction,
            )
            out.update(allocs)

        return out

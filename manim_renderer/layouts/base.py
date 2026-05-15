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

    `subject_host_id` (PR W) is set for `annotation` members that point at
    a host via `params.subject`. The solver uses it to reserve a side
    region of the host's slot for the callout, shrinking the host.
    """
    id: str
    role: str
    preferred_size: tuple[float, float]
    slot: str | None = None
    subject_host_id: str | None = None


# Gap between a host's allocated region and a subject-bound callout
# carved out of the same slot. Matches `resolvers/anchor.DEFAULT_ANCHOR_BUFF`
# so visual spacing is consistent with anchor-based placement.
_SUBJECT_CALLOUT_GAP: float = 0.5


def _split_for_subject(
    slot: Rect,
    callout_size: tuple[float, float],
    fmt: str,
) -> tuple[Rect, Rect]:
    """Carve a `callout_size`-shaped region from one side of `slot` and
    return `(host_container, callout_rect)`.

    Horizontal format: callout reserved on the right; host gets the left
    region. Vertical format: callout reserved at the bottom; host gets
    the top region. The host_container shrinks by `callout_w + gap` (or
    `callout_h + gap`).
    """
    gap = _SUBJECT_CALLOUT_GAP
    cw, ch = callout_size

    if fmt == "vertical":
        # Stack: host on top, callout on bottom.
        reserve_h = min(ch, slot.height - gap - 0.1)
        reserve_h = max(0.1, reserve_h)
        host_h = max(0.1, slot.height - reserve_h - gap)
        host_cy = slot.cy + reserve_h / 2.0 + gap / 2.0
        callout_cy = slot.cy - host_h / 2.0 - gap / 2.0
        host_container = Rect(
            cx=slot.cx, cy=host_cy, width=slot.width, height=host_h,
        )
        callout_rect = Rect(
            cx=slot.cx, cy=callout_cy, width=min(cw, slot.width),
            height=reserve_h,
        )
        return host_container, callout_rect

    # Horizontal: host on left, callout on right.
    reserve_w = min(cw, slot.width - gap - 0.1)
    reserve_w = max(0.1, reserve_w)
    host_w = max(0.1, slot.width - reserve_w - gap)
    host_cx = slot.cx - reserve_w / 2.0 - gap / 2.0
    callout_cx = slot.cx + host_w / 2.0 + gap / 2.0
    host_container = Rect(
        cx=host_cx, cy=slot.cy, width=host_w, height=slot.height,
    )
    callout_rect = Rect(
        cx=callout_cx, cy=slot.cy, width=reserve_w,
        height=min(ch, slot.height),
    )
    return host_container, callout_rect


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
          * Each slot is solved independently. Members within a slot are
            laid out via `flex_solve` along the layout's per-direction
            axis (see `_LAYOUT_FLEX_DIRECTION`).
          * Subject-bound annotations (`subject_host_id` set) reserve a
            side region of their host's slot; the host(s) flex-solve in
            the remaining inner region.
          * Members without a slot AND no subject host (legacy anchored
            callouts) are NOT placed by the solver — the runner keeps
            their static anchor.
          * Roles drive `preferred_size`, which the solver consumes (PR W).
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

            # PR W: split visible members into subject-bound annotations
            # vs everything else. The annotations reserve a side region;
            # the hosts flex-solve in the shrunken interior.
            subject_annotations = [
                m for m in visible
                if m.role == "annotation" and m.subject_host_id is not None
                and any(h.id == m.subject_host_id for h in visible)
            ]
            non_subject = [
                m for m in visible if m not in subject_annotations
            ]

            host_container = slot_rect
            if subject_annotations:
                # For each subject annotation, carve out a side rect and
                # shrink host_container accordingly. Currently supports
                # one annotation per slot; multi-annotation falls back to
                # stacking on the same side.
                ann = subject_annotations[0]
                host_container, callout_rect = _split_for_subject(
                    slot_rect, ann.preferred_size, self.format,
                )
                # Place all subject annotations in the reserved region
                # (stacked if more than one).
                if len(subject_annotations) == 1:
                    out[ann.id] = callout_rect
                else:
                    ann_dir = "vertical"
                    ann_allocs = flex_solve(
                        [(a.id, a.role, a.preferred_size)
                         for a in subject_annotations],
                        container=callout_rect,
                        direction=ann_dir,
                    )
                    out.update(ann_allocs)

            if non_subject:
                allocs = flex_solve(
                    [(m.id, m.role, m.preferred_size) for m in non_subject],
                    container=host_container,
                    direction=direction,
                )
                out.update(allocs)

        return out

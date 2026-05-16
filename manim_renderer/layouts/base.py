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


# Round 3 — per-layout "primary content slot". When an overlay show event
# arrives with no anchor, subject, or explicit slot, the runner falls back
# to this slot so the solver actually places the component. Without this
# map, overlay components stack at the origin (their natural mobject
# build position) because `Layout.solve` skips members with slot=None.
PRIMARY_SLOT: dict[str, str] = {
    "hero":       "main",
    "split":      "left",
    "stacked":    "top",
    "data-left":  "body",
    "data-top":   "body",
    "trio":       "A",
    "trio-stack": "A",
    "title-body": "body",
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
    # Round 3 — when the callout came from `anchor: "<token>:host"`, the
    # token (above/below/left-of/right-of) is recorded here so the solver
    # can place the callout on the author-specified side. None means the
    # callout used `subject:` and the solver picks the side itself.
    anchor_side: str | None = None


# Gap between a host's allocated region and a subject-bound callout
# carved out of the same slot. Matches `resolvers/anchor.DEFAULT_ANCHOR_BUFF`
# so visual spacing is consistent with anchor-based placement.
_SUBJECT_CALLOUT_GAP: float = 0.5


def _pack_host_with_subject(
    slot: Rect,
    host_size: tuple[float, float],
    callout_size: tuple[float, float],
    fmt: str,
    gap: float = _SUBJECT_CALLOUT_GAP,
    anchor_side: str | None = None,
) -> tuple[Rect, Rect]:
    """Pack a host + its annotation callout as a centered group inside `slot`.

    Both rects are sized to their `preferred_size` (clamped if the pair
    overflows the slot). The pair is laid out along the carve axis with
    exactly `gap` between them, then the combined block is centered in
    the slot. Cross-axis: both rects sit at the slot's cross-axis center.

    `anchor_side` (Round 3): when set to `"above"`, `"below"`, `"left-of"`,
    or `"right-of"`, the callout takes that side regardless of layout
    format — this supports `anchor:`-based callouts where the author
    chose the side explicitly. When `None`, the default is:
        - horizontal format → callout on right (left-to-right pair)
        - vertical format   → callout below (top-to-bottom pair)
    """
    hw, hh = host_size
    cw, ch = callout_size

    if anchor_side is None:
        side = "below" if fmt == "vertical" else "right-of"
    else:
        side = anchor_side

    if side in ("above", "below"):
        # Carve axis = y. Pair runs top→bottom; `below` puts host above.
        combined = hh + gap + ch
        if combined > slot.height:
            scale = slot.height / combined
            hh *= scale
            ch *= scale
            combined = hh + gap + ch
        top_edge = slot.cy + combined / 2.0
        if side == "below":
            host_cy = top_edge - hh / 2.0
            callout_cy = top_edge - hh - gap - ch / 2.0
        else:  # "above"
            callout_cy = top_edge - ch / 2.0
            host_cy = top_edge - ch - gap - hh / 2.0
        host_w = min(hw, slot.width)
        callout_w = min(cw, slot.width)
        return (
            Rect(cx=slot.cx, cy=host_cy, width=host_w, height=hh),
            Rect(cx=slot.cx, cy=callout_cy, width=callout_w, height=ch),
        )

    # Horizontal sides — carve axis = x. Pair runs left→right.
    combined = hw + gap + cw
    if combined > slot.width:
        scale = slot.width / combined
        hw *= scale
        cw *= scale
        combined = hw + gap + cw
    left_edge = slot.cx - combined / 2.0
    if side == "right-of" or (anchor_side is None and fmt != "vertical"):
        host_cx = left_edge + hw / 2.0
        callout_cx = left_edge + hw + gap + cw / 2.0
    else:  # "left-of"
        callout_cx = left_edge + cw / 2.0
        host_cx = left_edge + cw + gap + hw / 2.0
    host_h = min(hh, slot.height)
    callout_h = min(ch, slot.height)
    return (
        Rect(cx=host_cx, cy=slot.cy, width=hw, height=host_h),
        Rect(cx=callout_cx, cy=slot.cy, width=cw, height=callout_h),
    )


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
                # PR W2: pack host + callout as a centered group. Only the
                # first annotation participates in the pack; additional
                # annotations stack on the same side of the host.
                ann = subject_annotations[0]
                host_member = next(
                    (m for m in non_subject if m.id == ann.subject_host_id),
                    None,
                )
                host_pref = (
                    host_member.preferred_size if host_member
                    else (slot_rect.width, slot_rect.height)
                )
                host_rect, callout_rect = _pack_host_with_subject(
                    slot_rect, host_pref, ann.preferred_size, self.format,
                    anchor_side=ann.anchor_side,
                )
                if host_member is not None:
                    out[host_member.id] = host_rect
                    # Drop the host from non_subject so the lone-primary
                    # passthrough below doesn't overwrite it.
                    non_subject = [
                        m for m in non_subject if m.id != host_member.id
                    ]
                if len(subject_annotations) == 1:
                    out[ann.id] = callout_rect
                else:
                    ann_allocs = flex_solve(
                        [(a.id, a.role, a.preferred_size)
                         for a in subject_annotations],
                        container=callout_rect,
                        direction="vertical",
                    )
                    out.update(ann_allocs)
                # Remaining non_subject members (rare: a sibling primary
                # in the same slot) flex inside the shrunken host_container.
                host_container = host_rect

            if non_subject:
                # PR W2: lone primary/hero with no subject annotations gets
                # the full host_container (= slot rect when no subject pack
                # happened) verbatim. Restores Phase 1 "title fills its
                # slot" behavior while preserving role-driven shrinking for
                # supporting/ambient and multi-member slots.
                if (
                    len(non_subject) == 1
                    and non_subject[0].role in ("primary", "hero")
                    and not subject_annotations
                ):
                    out[non_subject[0].id] = host_container
                else:
                    allocs = flex_solve(
                        [(m.id, m.role, m.preferred_size) for m in non_subject],
                        container=host_container,
                        direction=direction,
                    )
                    out.update(allocs)

        return out

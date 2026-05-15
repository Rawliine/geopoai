"""PR J — `split` (horizontal) and `stacked` (vertical) layouts as solvers.

Three contracts:
  * Single component per slot returns the slot rect verbatim (backward
    compat — Phase 1 PD scenes render identically).
  * Two primaries in the same slot get side-by-side via `flex_solve`
    along the layout's flex axis.
  * `hidden` cast members occupy no space and don't get a Rect.

The deeper "primary + annotation 60/40 redistribution" case lives in
PR L (subject-based callouts) — slots currently can't host callouts.
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts.base import CastMember
from manim_renderer.layouts.resolver import resolve_layout


def _cast(*entries: tuple[str, str, str | None, tuple[float, float]]) -> list[CastMember]:
    return [
        CastMember(id=id_, role=role, slot=slot, preferred_size=size)
        for id_, role, slot, size in entries
    ]


# --- split (horizontal) ---------------------------------------------------


def test_split_one_per_slot_matches_static_rects():
    layout = resolve_layout("split", "horizontal")
    cast = _cast(
        ("a", "primary", "left",  (3.0, 2.0)),
        ("b", "primary", "right", (3.0, 2.0)),
    )
    out = layout.solve(cast)

    assert out["a"] == layout.slots["left"]
    assert out["b"] == layout.slots["right"]


def test_split_two_primaries_in_same_slot_side_by_side():
    layout = resolve_layout("split", "horizontal")
    cast = _cast(
        ("a", "primary", "left", (3.0, 2.0)),
        ("b", "primary", "left", (3.0, 2.0)),
    )
    out = layout.solve(cast)

    assert set(out) == {"a", "b"}
    left_rect = layout.slots["left"]
    # Both rects sit inside the left slot.
    for rect in out.values():
        assert abs(rect.cx - left_rect.cx) <= left_rect.width
    # a is to the left of b (cast order = on-screen order).
    assert out["a"].cx < out["b"].cx


def test_split_hidden_member_takes_no_space():
    layout = resolve_layout("split", "horizontal")
    cast = _cast(
        ("a", "primary", "left", (3.0, 2.0)),
        ("ghost", "hidden", "left", (0.0, 0.0)),
    )
    out = layout.solve(cast)

    # Single visible primary in slot → owns slot rect.
    assert out["a"] == layout.slots["left"]
    assert "ghost" not in out


def test_split_no_slot_members_excluded():
    """Anchored callouts (slot=None) are NOT placed by the solver.
    Their position is managed by `place_at_anchor` + `position_finalized`
    today; PR L lifts that into the solver."""
    layout = resolve_layout("split", "horizontal")
    cast = _cast(
        ("a", "primary",    "left",  (3.0, 2.0)),
        ("b", "primary",    "right", (3.0, 2.0)),
        ("note", "annotation", None,  (2.0, 1.0)),
    )
    out = layout.solve(cast)

    assert "note" not in out
    assert out["a"] == layout.slots["left"]
    assert out["b"] == layout.slots["right"]


# --- stacked (vertical) ---------------------------------------------------


def test_stacked_one_per_slot_matches_static_rects():
    layout = resolve_layout("stacked", "vertical")
    cast = _cast(
        ("a", "primary", "top",    (2.0, 3.0)),
        ("b", "primary", "bottom", (2.0, 3.0)),
    )
    out = layout.solve(cast)

    assert out["a"] == layout.slots["top"]
    assert out["b"] == layout.slots["bottom"]


def test_stacked_two_in_same_slot_flex_vertically():
    layout = resolve_layout("stacked", "vertical")
    cast = _cast(
        ("a", "primary", "top", (2.0, 2.0)),
        ("b", "primary", "top", (2.0, 2.0)),
    )
    out = layout.solve(cast)

    # Cast order = top-to-bottom on screen. a sits above b.
    assert out["a"].cy > out["b"].cy
    # Both inside the top slot's vertical extent.
    top = layout.slots["top"]
    for rect in out.values():
        assert abs(rect.cy - top.cy) <= top.height

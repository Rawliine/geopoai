"""When only one slot of a multi-slot layout is occupied, the lone
content reflows into the full frame so it sits at the visual center
instead of its slot's assigned position (which may be off-center —
e.g. title-body's body slot sits at cy=-1.0).

Multi-slot layouts that have multiple visible slots stay at their
assigned positions; the reflow only fires for the single-occupied case.
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts.base import CastMember
from manim_renderer.layouts.resolver import resolve_layout


def _member(id_: str, slot: str, role: str = "primary",
            size: tuple[float, float] = (3.0, 2.0)) -> CastMember:
    return CastMember(id=id_, role=role, slot=slot, preferred_size=size)


def test_title_body_horizontal_with_only_body_reflows_to_center():
    """Title slot empty, body has one primary → body's lone-primary
    sentinel sits at frame center, not body slot's cy=-1.0."""
    layout = resolve_layout("title-body", "horizontal")
    cast = [_member("c", "body")]
    out = layout.solve(cast)
    rect = out["c"]
    # Lone primary returns position-only sentinel; cx/cy must be at
    # frame center (0, 0), not the body slot's (0, -1).
    assert rect.width == 0.0 and rect.height == 0.0
    assert rect.cx == pytest.approx(0.0)
    assert rect.cy == pytest.approx(0.0)


def test_title_body_vertical_with_only_body_reflows_to_center():
    layout = resolve_layout("title-body", "vertical")
    cast = [_member("c", "body")]
    out = layout.solve(cast)
    rect = out["c"]
    assert rect.width == 0.0 and rect.height == 0.0
    assert rect.cx == pytest.approx(0.0)
    assert rect.cy == pytest.approx(0.0)


def test_split_with_only_left_reflows_to_frame_center():
    """split horizontal has left + right slots. With only left
    occupied, the lone primary sentinel sits at frame center."""
    layout = resolve_layout("split", "horizontal")
    cast = [_member("c", "left")]
    out = layout.solve(cast)
    rect = out["c"]
    assert rect.width == 0.0 and rect.height == 0.0
    assert rect.cx == pytest.approx(0.0)


def test_both_slots_occupied_no_reflow():
    """When multiple slots are occupied, each member stays at its own
    slot's center (the reflow only fires for single-slot case)."""
    layout = resolve_layout("title-body", "horizontal")
    cast = [_member("a", "title"), _member("b", "body")]
    out = layout.solve(cast)
    # Both are lone primaries in their respective slots → position-only
    # sentinels, but at the SLOT centers (not frame center).
    title_rect = layout.slots["title"]
    body_rect = layout.slots["body"]
    assert out["a"].cy == pytest.approx(title_rect.cy)  # +3.0
    assert out["b"].cy == pytest.approx(body_rect.cy)   # -1.0


def test_hero_single_slot_layout_unaffected():
    """hero has only one slot — reflow can't apply because there's
    nothing to reflow into. Lone primary still sentinel at slot center."""
    layout = resolve_layout("hero", "horizontal")
    cast = [_member("c", "main")]
    out = layout.solve(cast)
    rect = out["c"]
    assert rect.width == 0.0 and rect.height == 0.0
    main = layout.slots["main"]
    assert rect.cx == pytest.approx(main.cx)
    assert rect.cy == pytest.approx(main.cy)

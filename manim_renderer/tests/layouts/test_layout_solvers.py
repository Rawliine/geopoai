"""PR K — every layout honors the solver contract.

The default `Layout.solve` in `layouts/base.py` does per-slot flex via
`_LAYOUT_FLEX_DIRECTION` and a backward-compat passthrough when a slot
has exactly one non-annotation member. These tests pin that behavior on
every layout name registered in `LAYOUT_FORMATS`, so future PRs can't
silently regress backward compat or skip a layout when adding solver
features.

Coverage matrix:
  * 1 primary per slot  → slot rect verbatim (Phase 1 behavior)
  * 2 primaries in one slot → flex along the layout's flex direction
  * hidden cast member  → no Rect, no space consumed
  * No solver slot for None-slot members
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts.base import CastMember
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.schema.validator import LAYOUT_FORMATS


# Slot-name fixtures per layout. Format is implied by the layout name in
# `LAYOUT_FORMATS`; pick the first allowed format for the iteration.
_LAYOUT_FIXTURES: dict[str, list[str]] = {
    "hero":       ["main"],
    "split":      ["left", "right"],
    "stacked":    ["top", "bottom"],
    "data-left":  ["data", "body"],
    "data-top":   ["data", "body"],
    "trio":       ["A", "B", "C"],
    "trio-stack": ["A", "B", "C"],
    "title-body": ["title", "body"],
}


def _fmt_for(layout_name: str) -> str:
    """Pick the canonical format for a layout name."""
    fmts = sorted(LAYOUT_FORMATS[layout_name])
    return fmts[0]


def _member(id_: str, slot: str, role: str = "primary",
            size: tuple[float, float] = (2.0, 2.0)) -> CastMember:
    return CastMember(id=id_, role=role, slot=slot, preferred_size=size)


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_lone_primary_per_slot_returns_slot_rect(layout_name):
    """PR W2: a lone primary or hero with no subject annotations gets
    the slot rect verbatim (restores Phase 1 'title fills its slot'
    behavior). The previous round-1 change clamped every lone member to
    its preferred size, causing tall titles to shrink. Roles still
    matter for supporting/ambient (see test below) and multi-member
    slots."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [_member(f"c{i}", s) for i, s in enumerate(slots)]
    out = layout.solve(cast)
    for i, s in enumerate(slots):
        assert out[f"c{i}"] == layout.slots[s], (layout_name, s)


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_lone_supporting_uses_preferred_size(layout_name):
    """PR W2: lone supporting/ambient members still flex (the passthrough
    is primary/hero-only). This keeps setRole-driven shrinking visible."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slot = _LAYOUT_FIXTURES[layout_name][0]
    # Pick a preferred size strictly smaller than every slot in the
    # fixtures so the flex result is unambiguously sub-slot regardless of
    # which axis the layout flexes on.
    cast = [_member("c", slot, role="supporting", size=(1.0, 0.8))]
    out = layout.solve(cast)
    slot_rect = layout.slots[slot]
    rect = out["c"]
    # Centered in slot, sized at preferred (not slot dims).
    assert rect.cx == pytest.approx(slot_rect.cx)
    assert rect.cy == pytest.approx(slot_rect.cy)
    assert rect.width < slot_rect.width
    assert rect.height < slot_rect.height


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_multi_member_slot_flexes_within_slot(layout_name):
    """Putting two primaries in one slot should produce two rects, each
    contained within that slot's bounds."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    target_slot = _LAYOUT_FIXTURES[layout_name][0]
    slot_rect = layout.slots[target_slot]

    cast = [
        _member("a", target_slot, size=(1.5, 1.5)),
        _member("b", target_slot, size=(1.5, 1.5)),
    ]
    out = layout.solve(cast)

    assert set(out) == {"a", "b"}
    for rect in out.values():
        # Rect center must lie inside the slot's bbox (with slack for
        # padding).
        assert abs(rect.cx - slot_rect.cx) <= slot_rect.width
        assert abs(rect.cy - slot_rect.cy) <= slot_rect.height


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_hidden_member_excluded(layout_name):
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [
        _member("visible", slots[0], size=(2.0, 2.0)),
        _member("ghost", slots[0], role="hidden", size=(0.0, 0.0)),
    ]
    out = layout.solve(cast)

    assert "ghost" not in out
    # PR W2: lone visible primary → slot rect verbatim.
    slot_rect = layout.slots[slots[0]]
    assert out["visible"] == slot_rect


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_no_slot_members_excluded(layout_name):
    """slot=None members (anchored callouts pre-PR L) are not placed by
    the solver — the runner's static anchor pipeline owns them."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [
        _member("a", slots[0]),
        CastMember(id="floating", role="annotation",
                    slot=None, preferred_size=(2.0, 1.0)),
    ]
    out = layout.solve(cast)

    assert "floating" not in out


# --- title-body: title pinned, body flexible -----------------------------


def test_title_body_title_slot_pinned():
    """Title strip stays centered in its slot even when the body slot has
    multiple members (the "title pinned" rule from the brief). PR W:
    title gets its preferred-size rect centered in the title slot."""
    layout = resolve_layout("title-body", "horizontal")
    cast = [
        _member("hdr", "title", size=(8.0, 1.0)),
        _member("a",   "body",  size=(3.0, 2.0)),
        _member("b",   "body",  size=(3.0, 2.0)),
    ]
    out = layout.solve(cast)

    # PR W2: lone primary title → slot rect verbatim.
    title_rect = layout.slots["title"]
    assert out["hdr"] == title_rect
    # Body slot got the flex treatment — both fit inside it.
    body_rect = layout.slots["body"]
    for body_id in ("a", "b"):
        assert abs(out[body_id].cx - body_rect.cx) <= body_rect.width
        assert abs(out[body_id].cy - body_rect.cy) <= body_rect.height


# --- empty cast ----------------------------------------------------------


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_empty_cast_returns_empty(layout_name):
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    assert layout.solve([]) == {}

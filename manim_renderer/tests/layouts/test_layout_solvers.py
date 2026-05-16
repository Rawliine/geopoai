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
def test_lone_primary_per_slot_returns_position_only_sentinel(layout_name):
    """A lone primary/hero with no subject annotations gets a
    position-only sentinel rect (width=0, height=0) at the slot's
    center. The runner reads the sentinel and centers the mobject at
    that point without scaling it, so a tall TextCard isn't shrunk to
    fit a short slot. Roles still matter for supporting/ambient (see
    next test) and multi-member slots."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [_member(f"c{i}", s) for i, s in enumerate(slots)]
    out = layout.solve(cast)
    for i, s in enumerate(slots):
        slot_rect = layout.slots[s]
        rect = out[f"c{i}"]
        assert rect.width == 0.0, (layout_name, s)
        assert rect.height == 0.0, (layout_name, s)
        assert rect.cx == pytest.approx(slot_rect.cx), (layout_name, s)
        assert rect.cy == pytest.approx(slot_rect.cy), (layout_name, s)


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_lone_supporting_uses_preferred_size(layout_name):
    """Lone supporting/ambient members still flex (the passthrough is
    primary/hero-only). Use two slots both populated to exercise the
    flex path without triggering the lone-occupied-slot reflow."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    if len(slots) == 1:
        # Single-slot layout (hero) — supporting member still flexes
        # inside the slot, no reflow possible.
        cast = [_member("c", slots[0], role="supporting", size=(1.0, 0.8))]
        out = layout.solve(cast)
        rect = out["c"]
        assert rect.width < layout.slots[slots[0]].width
        assert rect.height < layout.slots[slots[0]].height
        return
    # Multi-slot layout: pad an extra primary into a second slot so the
    # reflow doesn't fire (we're testing flex sizing, not reflow).
    cast = [
        _member("c", slots[0], role="supporting", size=(1.0, 0.8)),
        _member("filler", slots[1], role="primary", size=(1.0, 1.0)),
    ]
    out = layout.solve(cast)
    slot_rect = layout.slots[slots[0]]
    rect = out["c"]
    assert rect.cx == pytest.approx(slot_rect.cx)
    assert rect.cy == pytest.approx(slot_rect.cy)
    assert rect.width < slot_rect.width
    assert rect.height < slot_rect.height


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_multi_member_slot_flexes_within_slot(layout_name):
    """Putting two primaries in one slot produces two rects whose
    centers cluster around the flex container's center. For multi-slot
    layouts this test populates a sibling slot too, so the
    lone-occupied reflow doesn't fire and the container stays at its
    natural slot rect."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    target_slot = slots[0]
    slot_rect = layout.slots[target_slot]

    cast = [
        _member("a", target_slot, size=(1.5, 1.5)),
        _member("b", target_slot, size=(1.5, 1.5)),
    ]
    if len(slots) > 1:
        cast.append(_member("filler", slots[1], size=(1.0, 1.0)))
    out = layout.solve(cast)

    assert {"a", "b"} <= set(out)
    for key in ("a", "b"):
        rect = out[key]
        assert abs(rect.cx - slot_rect.cx) <= slot_rect.width
        assert abs(rect.cy - slot_rect.cy) <= slot_rect.height


@pytest.mark.parametrize("layout_name", list(_LAYOUT_FIXTURES.keys()))
def test_hidden_member_excluded(layout_name):
    """Hidden members never appear in the solver's output. Pads a
    sibling slot for multi-slot layouts so the lone-occupied reflow
    doesn't shift the visible member to frame center (that's tested
    separately in test_reflow_when_one_slot.py)."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [
        _member("visible", slots[0], size=(2.0, 2.0)),
        _member("ghost", slots[0], role="hidden", size=(0.0, 0.0)),
    ]
    if len(slots) > 1:
        cast.append(_member("sibling", slots[1], size=(1.0, 1.0)))
    out = layout.solve(cast)

    assert "ghost" not in out
    # Lone visible primary in slot 0 → position-only sentinel at the
    # slot's own center (sibling occupied → no full-frame reflow).
    slot_rect = layout.slots[slots[0]]
    rect = out["visible"]
    assert rect.width == 0.0
    assert rect.height == 0.0
    assert rect.cx == pytest.approx(slot_rect.cx)
    assert rect.cy == pytest.approx(slot_rect.cy)


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

    # Lone primary title → position-only sentinel at title slot center.
    title_rect = layout.slots["title"]
    hdr = out["hdr"]
    assert hdr.width == 0.0 and hdr.height == 0.0
    assert hdr.cx == pytest.approx(title_rect.cx)
    assert hdr.cy == pytest.approx(title_rect.cy)
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

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
def test_one_primary_per_slot_centered_at_preferred_size(layout_name):
    """PR W: a lone primary's rect is centered in its slot at the
    member's preferred size (not the full slot rect verbatim). The
    previous backward-compat passthrough silently swallowed role scaling."""
    fmt = _fmt_for(layout_name)
    layout = resolve_layout(layout_name, fmt)
    slots = _LAYOUT_FIXTURES[layout_name]
    cast = [_member(f"c{i}", s) for i, s in enumerate(slots)]
    out = layout.solve(cast)
    for i, s in enumerate(slots):
        slot_rect = layout.slots[s]
        rect = out[f"c{i}"]
        # Same center as the slot.
        assert rect.cx == pytest.approx(slot_rect.cx), (layout_name, s)
        assert rect.cy == pytest.approx(slot_rect.cy), (layout_name, s)
        # Preferred (2,2) is used unless the slot is smaller along the
        # flex axis (e.g. title-body's 1.5-tall title strip clamps to 1.5).
        assert rect.width <= 2.0 + 1e-6, (layout_name, s)
        assert rect.height <= 2.0 + 1e-6, (layout_name, s)
        # Never collapses to zero.
        assert rect.width > 0 and rect.height > 0, (layout_name, s)


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
    # The lone visible primary centered at preferred size (or clamped to
    # the smaller slot axis — see title-body's 1.5-tall title strip).
    slot_rect = layout.slots[slots[0]]
    rect = out["visible"]
    assert rect.cx == pytest.approx(slot_rect.cx)
    assert rect.cy == pytest.approx(slot_rect.cy)
    assert rect.width > 0 and rect.height > 0


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

    # Title rect centered in the title slot at preferred size.
    title_rect = layout.slots["title"]
    assert out["hdr"].cx == pytest.approx(title_rect.cx)
    assert out["hdr"].cy == pytest.approx(title_rect.cy)
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

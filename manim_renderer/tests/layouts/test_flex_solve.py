"""PR I — `flex_solve` allocates a cast inside a container along an axis.

The solver is pure-math (no Manim mobjects). These tests pin the
contract that PR J+ relies on:

  * One primary in a container fills the container minus gap budget.
  * Two primaries split the main axis 50/50 with the gap.
  * Primary + annotation share the axis proportional to their preferred
    sizes (NOT a hard 60/40 — the solver isn't role-aware in PR I, that
    rebalancing lives at the layout-level in PR J+).
  * Oversized cast shrinks proportionally so the sum fits.
  * Empty cast returns `{}`.
  * Gap is honored between adjacent entries.
  * `hidden` entries (preferred size 0) are filtered out cleanly.
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts._flex import MIN_DIM, flex_solve
from manim_renderer.layouts.base import Rect


def _container(w: float = 12.0, h: float = 6.0) -> Rect:
    return Rect(cx=0.0, cy=0.0, width=w, height=h)


# --- happy path ---------------------------------------------------------


def test_empty_cast_returns_empty_dict():
    assert flex_solve([], container=_container(), direction="horizontal") == {}


def test_one_primary_centered_horizontal():
    out = flex_solve(
        [("a", "primary", (3.0, 2.0))],
        container=_container(),
        direction="horizontal",
    )
    assert set(out) == {"a"}
    assert out["a"].cx == pytest.approx(0.0)
    assert out["a"].cy == pytest.approx(0.0)
    assert out["a"].width == pytest.approx(3.0)
    assert out["a"].height == pytest.approx(2.0)


def test_two_primaries_split_50_50_horizontal():
    out = flex_solve(
        [("a", "primary", (3.0, 2.0)), ("b", "primary", (3.0, 2.0))],
        container=_container(),
        direction="horizontal",
        gap=0.5,
    )
    # Cast order maps to on-screen order; a is left of b.
    assert out["a"].cx < out["b"].cx
    # Symmetric around container center.
    assert out["a"].cx == pytest.approx(-out["b"].cx)
    # Gap between them.
    spacing = out["b"].cx - out["a"].cx - (out["a"].width / 2 + out["b"].width / 2)
    assert spacing == pytest.approx(0.5)


def test_two_primaries_split_50_50_vertical_top_to_bottom():
    out = flex_solve(
        [("a", "primary", (2.0, 3.0)), ("b", "primary", (2.0, 3.0))],
        container=_container(w=6.0, h=12.0),
        direction="vertical",
        gap=0.5,
    )
    # a is above b (higher cy in y-up Manim space).
    assert out["a"].cy > out["b"].cy


def test_primary_plus_annotation_proportional():
    """flex_solve allocates by preferred size — the solver itself doesn't
    know about role weights. With preferred 4.0 + 2.0 and a 12 container,
    the primary gets ~4/6 of the visible budget after gap."""
    out = flex_solve(
        [("main", "primary", (4.0, 2.0)),
         ("note", "annotation", (2.0, 2.0))],
        container=_container(),
        direction="horizontal",
        gap=0.5,
    )
    # Preferred fits within container, no scaling.
    assert out["main"].width == pytest.approx(4.0)
    assert out["note"].width == pytest.approx(2.0)
    # Combined extents + gap centered on container.
    left = out["main"].cx - out["main"].width / 2
    right = out["note"].cx + out["note"].width / 2
    assert (left + right) / 2 == pytest.approx(0.0)


def test_oversized_cast_shrinks_proportionally():
    """Sum (5 + 5 + 5 + gaps 1.0) = 16 > container 12 along main axis.
    Each entry should shrink uniformly so the sum + gaps == 12."""
    out = flex_solve(
        [("a", "primary", (5.0, 2.0)),
         ("b", "primary", (5.0, 2.0)),
         ("c", "primary", (5.0, 2.0))],
        container=_container(w=12.0, h=6.0),
        direction="horizontal",
        gap=0.5,
    )
    total_width = sum(r.width for r in out.values()) + 2 * 0.5  # 2 gaps
    assert total_width == pytest.approx(12.0, abs=1e-6)
    # All three got the same width since their preferred widths were equal.
    widths = [out["a"].width, out["b"].width, out["c"].width]
    assert max(widths) - min(widths) < 1e-6


def test_min_dim_floor_on_extreme_shrink():
    """Cast that demands 100× the container should still produce visible
    rects (not shrink to zero)."""
    out = flex_solve(
        [("a", "primary", (1000.0, 2.0)), ("b", "primary", (1000.0, 2.0))],
        container=_container(w=1.0, h=6.0),
        direction="horizontal",
        gap=0.0,
    )
    for rect in out.values():
        assert rect.width >= MIN_DIM
        assert rect.height >= MIN_DIM


def test_hidden_entries_filtered_out():
    """Entries with preferred size (0, 0) — i.e. role=hidden — are dropped
    before allocation. They don't get a Rect, don't consume space."""
    out = flex_solve(
        [("a", "primary", (3.0, 2.0)),
         ("hidden", "hidden", (0.0, 0.0)),
         ("b", "primary", (3.0, 2.0))],
        container=_container(),
        direction="horizontal",
        gap=0.5,
    )
    assert "hidden" not in out
    assert set(out) == {"a", "b"}


def test_gap_widens_separation():
    out_tight = flex_solve(
        [("a", "primary", (2.0, 1.0)), ("b", "primary", (2.0, 1.0))],
        container=_container(),
        direction="horizontal",
        gap=0.0,
    )
    out_wide = flex_solve(
        [("a", "primary", (2.0, 1.0)), ("b", "primary", (2.0, 1.0))],
        container=_container(),
        direction="horizontal",
        gap=2.0,
    )
    tight_spacing = out_tight["b"].cx - out_tight["a"].cx
    wide_spacing = out_wide["b"].cx - out_wide["a"].cx
    assert wide_spacing > tight_spacing


def test_cross_axis_centered():
    out = flex_solve(
        [("a", "primary", (3.0, 2.0))],
        container=Rect(cx=1.0, cy=2.0, width=6.0, height=4.0),
        direction="horizontal",
    )
    # Cross axis (y for horizontal) centered on container.cy.
    assert out["a"].cy == pytest.approx(2.0)


# --- align variants ----------------------------------------------------


def test_align_start_horizontal():
    out = flex_solve(
        [("a", "primary", (3.0, 2.0))],
        container=_container(w=10.0, h=6.0),
        direction="horizontal",
        align="start",
    )
    # Left edge hugs container's left edge.
    assert out["a"].cx - out["a"].width / 2 == pytest.approx(-5.0)


def test_align_end_horizontal():
    out = flex_solve(
        [("a", "primary", (3.0, 2.0))],
        container=_container(w=10.0, h=6.0),
        direction="horizontal",
        align="end",
    )
    assert out["a"].cx + out["a"].width / 2 == pytest.approx(5.0)


def test_align_start_vertical_means_top():
    """Vertical start = top (positive y in Manim's y-up coords)."""
    out = flex_solve(
        [("a", "primary", (2.0, 3.0))],
        container=_container(w=6.0, h=10.0),
        direction="vertical",
        align="start",
    )
    # Top edge at container top.
    assert out["a"].cy + out["a"].height / 2 == pytest.approx(5.0)

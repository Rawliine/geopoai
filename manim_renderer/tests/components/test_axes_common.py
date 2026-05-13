"""Tests for the pure-math layer of _axes_common.

Mobject construction (the `Axes2D` class) is exercised indirectly through the
BarChart/LineChart tests; this file pins down the geometry math that both
chart components depend on.
"""

from __future__ import annotations

import math

import pytest

from manim_renderer.components.data_viz._axes_common import (
    compute_plot_area,
    make_category_to_x,
    make_value_to_x,
    make_value_to_y,
    nice_ticks,
)


# --- plot area --------------------------------------------------------------

def test_plot_area_inside_bbox():
    p = compute_plot_area(10.0, 5.0)
    # Plot rect must be inside the bbox by at least the minimum margins.
    assert -5.0 < p.left < p.right < 5.0
    assert -2.5 < p.bottom < p.top < 2.5
    assert p.width > 0 and p.height > 0


def test_y_title_widens_left_margin():
    no_title = compute_plot_area(10.0, 5.0, has_y_title=False)
    with_title = compute_plot_area(10.0, 5.0, has_y_title=True)
    assert with_title.left > no_title.left  # plot pushed further right


def test_x_title_widens_bottom_margin():
    no_title = compute_plot_area(10.0, 5.0, has_x_title=False)
    with_title = compute_plot_area(10.0, 5.0, has_x_title=True)
    assert with_title.bottom > no_title.bottom  # plot pushed further up


# --- value mappers ----------------------------------------------------------

def test_value_to_y_endpoints():
    p = compute_plot_area(10.0, 5.0)
    to_y = make_value_to_y(p, 0.0, 100.0)
    assert math.isclose(to_y(0.0), p.bottom, abs_tol=1e-9)
    assert math.isclose(to_y(100.0), p.top, abs_tol=1e-9)


def test_value_to_y_midpoint():
    p = compute_plot_area(10.0, 5.0)
    to_y = make_value_to_y(p, 0.0, 100.0)
    mid = (p.bottom + p.top) / 2
    assert math.isclose(to_y(50.0), mid, abs_tol=1e-9)


def test_value_to_y_degenerate_range_uses_midline():
    p = compute_plot_area(10.0, 5.0)
    to_y = make_value_to_y(p, 5.0, 5.0)
    mid = (p.bottom + p.top) / 2
    assert math.isclose(to_y(5.0), mid)
    assert math.isclose(to_y(99.0), mid)  # safe rather than NaN


def test_value_to_x_endpoints():
    p = compute_plot_area(10.0, 5.0)
    to_x = make_value_to_x(p, 2000, 2020)
    assert math.isclose(to_x(2000), p.left)
    assert math.isclose(to_x(2020), p.right)


def test_category_to_x_spacing():
    p = compute_plot_area(10.0, 5.0)
    to_x = make_category_to_x(p, 4)
    xs = [to_x(i) for i in range(4)]
    # Centers should be evenly spaced and the gaps equal.
    gaps = [xs[i + 1] - xs[i] for i in range(3)]
    assert all(math.isclose(g, gaps[0], abs_tol=1e-9) for g in gaps)
    # First bar half a slot in from left; last half a slot in from right.
    slot_w = p.width / 4
    assert math.isclose(xs[0] - p.left, slot_w / 2, abs_tol=1e-9)
    assert math.isclose(p.right - xs[-1], slot_w / 2, abs_tol=1e-9)


def test_category_to_x_rejects_zero_categories():
    p = compute_plot_area(10.0, 5.0)
    with pytest.raises(ValueError):
        make_category_to_x(p, 0)


# --- nice ticks -------------------------------------------------------------

def test_nice_ticks_covers_range():
    ticks = nice_ticks(0, 100, 5)
    assert ticks[0] >= 0
    assert ticks[-1] <= 100
    # All step sizes equal.
    if len(ticks) >= 2:
        step = ticks[1] - ticks[0]
        for i in range(2, len(ticks)):
            assert math.isclose(ticks[i] - ticks[i - 1], step, abs_tol=1e-9)


def test_nice_ticks_uses_1_2_5_progression():
    ticks = nice_ticks(0, 10, 5)
    step = ticks[1] - ticks[0]
    # Step must be in {1,2,5} × 10^k
    magnitude = 10 ** math.floor(math.log10(step))
    residual = round(step / magnitude, 10)
    assert residual in (1.0, 2.0, 5.0, 10.0), f"step {step} (residual {residual})"


def test_nice_ticks_small_range():
    ticks = nice_ticks(0.0, 1.0, 4)
    assert all(0 <= t <= 1.0 + 1e-9 for t in ticks)
    assert len(ticks) >= 2


def test_nice_ticks_swaps_inverted_input():
    a = nice_ticks(0, 100, 5)
    b = nice_ticks(100, 0, 5)
    assert a == b


def test_nice_ticks_degenerate_range_single_value():
    assert nice_ticks(5.0, 5.0, 4) == [5.0]


def test_nice_ticks_rejects_zero_target_count():
    with pytest.raises(ValueError):
        nice_ticks(0, 100, 0)

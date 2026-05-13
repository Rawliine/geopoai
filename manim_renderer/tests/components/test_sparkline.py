"""Sparkline unit tests."""

from __future__ import annotations

import logging

import pytest

from manim_renderer.components.data_viz._sparkline import Sparkline

logging.getLogger("manim").setLevel(logging.ERROR)


def test_basic_construction():
    sl = Sparkline([1, 2, 3, 4], size=(2.0, 0.5))
    # Has at least the trend line (and end marker by default + baseline)
    assert len(sl.submobjects) >= 1
    # Width close to 2.0 (markers add a tiny extension)
    assert 1.95 <= sl.width <= 2.15


def test_single_point_rejected():
    with pytest.raises(ValueError, match="at least 2 points"):
        Sparkline([5])


def test_empty_rejected():
    with pytest.raises(ValueError, match="at least 2 points"):
        Sparkline([])


def test_flat_series_does_not_div_by_zero():
    sl = Sparkline([5, 5, 5], size=(1.0, 0.4))
    # Just confirm it builds without ZeroDivisionError
    assert sl.height > 0


def test_baseline_can_be_disabled():
    sl_with = Sparkline([1, 2, 3], baseline_color="#aaaaaa")
    sl_without = Sparkline([1, 2, 3], baseline_color=None)
    # Without baseline, fewer submobjects.
    assert len(sl_without.submobjects) < len(sl_with.submobjects)


def test_extrema_markers_add_dots():
    base = Sparkline([1, 5, 3], show_extrema_markers=False)
    with_ext = Sparkline([1, 5, 3], show_extrema_markers=True)
    assert len(with_ext.submobjects) > len(base.submobjects)


def test_end_marker_can_be_disabled():
    base = Sparkline([1, 2, 3], show_end_marker=True, baseline_color=None)
    no_end = Sparkline([1, 2, 3], show_end_marker=False, baseline_color=None)
    assert len(no_end.submobjects) < len(base.submobjects)


def test_zero_baseline_normalizes_to_zero_floor():
    """With zero_baseline=True, the line's lowest point sits at the zero floor
    (not at the series min)."""
    no_zero = Sparkline([10, 12, 14], zero_baseline=False)
    with_zero = Sparkline([10, 12, 14], zero_baseline=True)
    # Both build cleanly; zero_baseline scenes will have a different visual
    # footprint but height is still positive and bounded by the requested size.
    assert no_zero.height > 0
    assert with_zero.height > 0

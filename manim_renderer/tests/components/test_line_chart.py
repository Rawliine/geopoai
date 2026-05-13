"""LineChart unit tests. Construction + anchors + entrance plumbing."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.data_viz.line_chart import LineChart

logging.getLogger("manim").setLevel(logging.ERROR)


def _two_series():
    return [
        {"label": "USA", "color": "actor_a",
         "points": [[2010, 14], [2015, 18], [2020, 21]]},
        {"label": "China", "color": "actor_b",
         "points": [[2010, 6], [2015, 11], [2020, 17]]},
    ]


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    assert lc.id == "c"
    assert len(lc._lines) == 2


def test_requires_series():
    with pytest.raises(ValueError, match="series"):
        LineChart({"id": "c"}, format="horizontal")


def test_rejects_empty_series():
    with pytest.raises(ValueError, match="series"):
        LineChart({"id": "c", "series": []}, format="horizontal")


def test_rejects_too_few_points():
    bad = [{"label": "a", "points": [[1, 2]]}]
    with pytest.raises(ValueError, match="at least 2"):
        LineChart({"id": "c", "series": bad}, format="horizontal")


def test_unknown_color_raises():
    bad = [{"label": "a", "color": "puce",
            "points": [[0, 0], [1, 1]]}]
    with pytest.raises(ValueError, match="palette key"):
        LineChart({"id": "c", "series": bad}, format="horizontal")


def test_unknown_value_format_raises():
    with pytest.raises(ValueError, match="value_format"):
        LineChart(
            {"id": "c", "series": _two_series(), "value_format": "lobster"},
            format="horizontal",
        )


# --- both formats -----------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    lc = LineChart(
        {"id": "c", "series": _two_series(),
         "x_axis": {"label": "Year"}, "y_axis": {"label": "GDP"}},
        format=fmt,
    )
    assert lc.width > 0 and lc.height > 0


# --- color rotation ---------------------------------------------------------

def test_color_rotation_when_color_omitted():
    series = [
        {"label": "a", "points": [[0, 0], [1, 1]]},
        {"label": "b", "points": [[0, 0], [1, 2]]},
        {"label": "c", "points": [[0, 0], [1, 3]]},
    ]
    lc = LineChart({"id": "c", "series": series}, format="horizontal")
    assert len(set(lc._series_colors)) == 3


# --- anchors ----------------------------------------------------------------

def test_series_end_anchor_by_index():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    coord = lc.get_anchor("series:0.end")
    assert coord.shape == (3,)
    np.testing.assert_array_almost_equal(coord, lc._lines[0].get_end())


def test_series_start_anchor_by_label():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    coord = lc.get_anchor("series:China.start")
    np.testing.assert_array_almost_equal(coord, lc._lines[1].get_start())


def test_series_anchor_missing_suffix():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    with pytest.raises(KeyError, match="suffix"):
        lc.get_anchor("series:0")


def test_series_anchor_bad_suffix():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    with pytest.raises(KeyError, match="start.*end"):
        lc.get_anchor("series:0.middle")


def test_series_anchor_out_of_range():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    with pytest.raises(KeyError, match="out of range"):
        lc.get_anchor("series:9.end")


def test_series_anchor_unknown_label():
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    with pytest.raises(KeyError, match="no series"):
        lc.get_anchor("series:Mars.end")


# --- entrance ---------------------------------------------------------------

def test_draw_out_entrance():
    from manim import AnimationGroup
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    anim = lc.entrance("draw-out", "slow")
    assert isinstance(anim, AnimationGroup)


def test_level_by_level_entrance():
    from manim import AnimationGroup
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    anim = lc.entrance("level-by-level", "normal")
    assert isinstance(anim, AnimationGroup)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    lc = LineChart({"id": "c", "series": _two_series()}, format="horizontal")
    anim = lc.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

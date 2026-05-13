"""BarChart unit tests. Construction + anchors + entrance plumbing."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.data_viz.bar_chart import BarChart

logging.getLogger("manim").setLevel(logging.ERROR)


def _data(n=3):
    return [
        {"label": f"L{i}", "value": float((i + 1) * 10)}
        for i in range(n)
    ]


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    bc = BarChart(
        {"id": "c", "data": _data(3)},
        format="horizontal",
    )
    assert bc.id == "c"
    assert len(bc._bars) == 3
    # Default show_value_labels=True; we should have one label per bar.
    assert len(bc._value_labels) == 3


def test_requires_data():
    with pytest.raises(ValueError, match="data"):
        BarChart({"id": "c"}, format="horizontal")


def test_rejects_empty_data():
    with pytest.raises(ValueError, match="data"):
        BarChart({"id": "c", "data": []}, format="horizontal")


def test_unknown_value_format_raises():
    with pytest.raises(ValueError, match="value_format"):
        BarChart(
            {"id": "c", "data": _data(2), "value_format": "lobster"},
            format="horizontal",
        )


def test_unknown_color_raises():
    bad = [{"label": "x", "value": 1, "color": "puce"}]
    with pytest.raises(ValueError, match="palette key"):
        BarChart({"id": "c", "data": bad}, format="horizontal")


# --- both formats -----------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    bc = BarChart(
        {"id": "c", "data": _data(4),
         "y_axis": {"label": "GDP"}, "x_axis": {"label": "Country"}},
        format=fmt,
    )
    assert bc.width > 0 and bc.height > 0


# --- color rotation ---------------------------------------------------------

def test_color_rotation_when_color_omitted():
    bc = BarChart(
        {"id": "c", "data": [
            {"label": "a", "value": 1},
            {"label": "b", "value": 2},
            {"label": "c", "value": 3},
        ]},
        format="horizontal",
    )
    # Three different colors rotated from the default cycle.
    assert len(set(bc._colors)) == 3


# --- value labels -----------------------------------------------------------

def test_value_labels_off():
    bc = BarChart(
        {"id": "c", "data": _data(3), "show_value_labels": False},
        format="horizontal",
    )
    assert bc._value_labels == []


# --- anchors ----------------------------------------------------------------

def test_bar_anchor_by_index():
    bc = BarChart({"id": "c", "data": _data(3)}, format="horizontal")
    coord = bc.get_anchor("bar:1")
    assert coord.shape == (3,)
    np.testing.assert_array_almost_equal(coord, bc._bars[1].get_top())


def test_bar_anchor_by_label():
    bc = BarChart({"id": "c", "data": _data(3)}, format="horizontal")
    coord = bc.get_anchor("bar:L2")
    np.testing.assert_array_almost_equal(coord, bc._bars[2].get_top())


def test_bar_anchor_out_of_range():
    bc = BarChart({"id": "c", "data": _data(2)}, format="horizontal")
    with pytest.raises(KeyError, match="out of range"):
        bc.get_anchor("bar:9")


def test_bar_anchor_unknown_label():
    bc = BarChart({"id": "c", "data": _data(2)}, format="horizontal")
    with pytest.raises(KeyError, match="no bar with label"):
        bc.get_anchor("bar:nonexistent")


def test_standard_anchors_inherited():
    bc = BarChart({"id": "c", "data": _data(2)}, format="horizontal")
    for name in ("top", "bottom", "left", "right", "center"):
        coord = bc.get_anchor(name)
        assert coord.shape == (3,)


# --- entrance ---------------------------------------------------------------

def test_count_up_entrance_returns_animation_group():
    from manim import AnimationGroup
    bc = BarChart({"id": "c", "data": _data(3)}, format="horizontal")
    anim = bc.entrance("count-up", "slow")
    assert isinstance(anim, AnimationGroup)


def test_grow_up_entrance():
    from manim import AnimationGroup
    bc = BarChart({"id": "c", "data": _data(2)}, format="horizontal")
    anim = bc.entrance("grow-up", "normal")
    assert isinstance(anim, AnimationGroup)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    bc = BarChart({"id": "c", "data": _data(2)}, format="horizontal")
    anim = bc.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

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


# --- Phase 2.0 / PR E2 — label positioning rules ----------------------------

def test_nonzero_labels_sit_above_their_own_bar():
    """Two-rule split: each non-zero label is just above its bar's top.
    The vertical offset (label.y - bar.top) is the same for every non-zero
    bar regardless of bar height — that's the consistency the user wanted."""
    bc = BarChart(
        {
            "id": "c",
            "data": [
                {"label": "A", "value": 1},
                {"label": "B", "value": 3},
                {"label": "C", "value": 5},
            ],
            "y_axis": {"min": 0, "max": 6, "ticks": 4},
        },
        format="horizontal",
    )
    offsets = [
        bc._value_labels[i].get_center()[1] - bc._bars[i].get_top()[1]
        for i in range(3)
    ]
    # All non-zero bars: same vertical offset (within numeric tolerance).
    assert max(offsets) - min(offsets) < 1e-6, (
        f"non-zero label offsets should be uniform; got {offsets}"
    )


def test_count_up_preserves_label_scene_position():
    """Phase 2.0 / PR E3 regression: `_BarValueLabel.set_value` must move
    `new_text` to the label's CURRENT scene center, not to the
    build-time LOCAL anchor_point. Failure mode: every count-up frame
    snaps the label to local coords, so when the parent BarChart is
    placed in a non-origin slot (e.g. split.right at cx=3.4), labels
    jump by `-slot.center` and appear outside the chart."""
    bc = BarChart(
        {
            "id": "c",
            "data": [{"label": "A", "value": 3}],
            "y_axis": {"min": 0, "max": 6, "ticks": 4},
        },
        format="horizontal",
    )
    # Simulate the scene runner placing the BarChart at split.right.
    bc.move_to([3.4, 0.0, 0.0])
    before = bc._value_labels[0]._text.get_center().copy()
    # Mid count-up frame.
    bc._value_labels[0].set_value(1.5)
    after = bc._value_labels[0]._text.get_center()
    # Position must be preserved. X may shift slightly if rendered widths
    # differ, but the label CENTER must stay at the same point so the
    # label appears above its bar, not outside the chart.
    np.testing.assert_allclose(after, before, atol=1e-6)


def test_zero_value_label_sits_at_floor():
    """Zero-value bars don't have a bar top to anchor against. The label
    sits at a fixed floor above the x-axis tick label band, NOT on the
    x-axis line where it would collide with `Outcome`/axis-title text."""
    bc = BarChart(
        {
            "id": "c",
            "data": [{"label": "Z", "value": 0}, {"label": "P", "value": 5}],
            "y_axis": {"min": 0, "max": 6, "ticks": 4},
        },
        format="horizontal",
    )
    # Zero-value label should be well above the baseline.
    plot_bottom = bc._axes.plot.bottom  # local-coord baseline
    zero_label_y = bc._value_labels[0].get_center()[1] - bc.get_center()[1]
    # Account for BarChart's move_to(ORIGIN) and the label being measured in
    # scene coords — translate back by component center.
    # The floor formula: baseline + label_height_est + 0.30. We just assert
    # the label is clearly above the baseline (not on or below it).
    # Compare scene-space y values directly using local-space baseline_y.
    baseline_y_scene = bc._bars[1].get_bottom()[1]  # bar #2 sits at baseline
    assert bc._value_labels[0].get_center()[1] > baseline_y_scene + 0.10, (
        "zero-value label must clear the x-axis label band"
    )


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

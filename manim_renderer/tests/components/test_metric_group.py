"""MetricGroup unit tests."""

from __future__ import annotations

import logging

import pytest

from manim_renderer.components.data_viz.metric_group import MetricGroup

logging.getLogger("manim").setLevel(logging.ERROR)


# --- construction ------------------------------------------------------------

def test_minimal_construction():
    mg = MetricGroup(
        {"id": "g", "stats": [
            {"value": 1, "label": "A"},
            {"value": 2, "label": "B"},
        ]},
        format="horizontal",
    )
    assert len(mg._stats) == 2
    assert mg.id == "g"


def test_requires_stats_list():
    with pytest.raises(ValueError, match="stats"):
        MetricGroup({"id": "g"}, format="horizontal")


def test_empty_stats_rejected():
    with pytest.raises(ValueError, match="stats"):
        MetricGroup({"id": "g", "stats": []}, format="horizontal")


# --- orientation defaults per format -----------------------------------------

def test_horizontal_default_orientation_is_row():
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    assert mg._orientation == "row"


def test_vertical_default_orientation_is_column():
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="vertical",
    )
    assert mg._orientation == "column"


def test_orientation_override():
    mg = MetricGroup(
        {"id": "g", "orientation": "column",
         "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    assert mg._orientation == "column"


def test_unknown_orientation_rejected():
    with pytest.raises(ValueError, match="orientation"):
        MetricGroup(
            {"id": "g", "orientation": "diagonal",
             "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
            format="horizontal",
        )


# --- shared styling inheritance ----------------------------------------------

def test_shared_value_format_inherited_by_children_without_override():
    mg = MetricGroup(
        {"id": "g", "value_format": "k",
         "stats": [
             {"value": 5000, "label": "A"},
             {"value": 8000, "label": "B", "value_format": "int"},  # override
         ]},
        format="horizontal",
    )
    assert mg._stats[0]._value_format == "k"
    assert mg._stats[1]._value_format == "int"


def test_color_scheme_actors_rotates():
    mg = MetricGroup(
        {"id": "g", "color_scheme": "actors",
         "stats": [{"value": 1, "label": str(i)} for i in range(3)]},
        format="horizontal",
    )
    assert mg._stats[0]._color_key == "actor_a"
    assert mg._stats[1]._color_key == "actor_b"
    assert mg._stats[2]._color_key == "actor_c"


def test_color_scheme_semantic_rotates():
    mg = MetricGroup(
        {"id": "g", "color_scheme": "semantic",
         "stats": [{"value": 1, "label": str(i)} for i in range(3)]},
        format="horizontal",
    )
    assert mg._stats[0]._color_key == "positive"
    assert mg._stats[1]._color_key == "neutral"
    assert mg._stats[2]._color_key == "negative"


def test_per_stat_color_overrides_scheme():
    mg = MetricGroup(
        {"id": "g", "color_scheme": "actors",
         "stats": [
             {"value": 1, "label": "A", "color": "highlight"},
             {"value": 2, "label": "B"},
         ]},
        format="horizontal",
    )
    assert mg._stats[0]._color_key == "highlight"
    assert mg._stats[1]._color_key == "actor_b"  # next in rotation


# --- anchors -----------------------------------------------------------------

def test_stat_anchor_by_index():
    mg = MetricGroup(
        {"id": "g", "stats": [
            {"value": 1, "label": "A"},
            {"value": 2, "label": "B"},
        ]},
        format="horizontal",
    )
    coord_0 = mg.get_anchor("stat:0")
    coord_1 = mg.get_anchor("stat:1")
    assert coord_0[0] < coord_1[0]  # 0 is to the left in row layout


def test_stat_anchor_by_id():
    mg = MetricGroup(
        {"id": "g", "stats": [
            {"id": "first", "value": 1, "label": "A"},
            {"id": "second", "value": 2, "label": "B"},
        ]},
        format="horizontal",
    )
    coord = mg.get_anchor("stat:second")
    assert coord[0] > 0  # right-of-center in row


def test_stat_anchor_out_of_range_raises():
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    with pytest.raises(KeyError, match="out of range"):
        mg.get_anchor("stat:5")


def test_stat_anchor_unknown_id_raises():
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    with pytest.raises(KeyError, match="no stat"):
        mg.get_anchor("stat:nonsense")


# --- extra_id_registrations --------------------------------------------------

def test_extra_id_registrations_exposes_named_children():
    mg = MetricGroup(
        {"id": "g", "stats": [
            {"id": "alpha", "value": 1, "label": "A"},
            {"value": 2, "label": "B"},  # no id, not exposed
            {"id": "gamma", "value": 3, "label": "C"},
        ]},
        format="horizontal",
    )
    extras = mg.extra_id_registrations()
    assert set(extras.keys()) == {"alpha", "gamma"}
    assert extras["alpha"] is mg._stats[0]
    assert extras["gamma"] is mg._stats[2]


# --- staggered entrance ------------------------------------------------------

def test_staggered_entrance_returns_lagged_start():
    from manim import LaggedStart
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    anim = mg.entrance("staggered", "normal")
    assert isinstance(anim, LaggedStart)


def test_other_entrance_dispatches_to_base():
    from manim import FadeIn
    mg = MetricGroup(
        {"id": "g", "stats": [{"value": 1, "label": "A"}, {"value": 2, "label": "B"}]},
        format="horizontal",
    )
    anim = mg.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)


# --- both formats ------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build_without_error(fmt):
    mg = MetricGroup(
        {"id": "g", "stats": [
            {"value": 1, "label": "A"},
            {"value": 2, "label": "B"},
            {"value": 3, "label": "C"},
        ]},
        format=fmt,
    )
    assert mg.width > 0 and mg.height > 0

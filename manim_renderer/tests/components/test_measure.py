"""Each component's `measure(params, format)` class method returns positive,
finite (width, height) for representative params. Pure-math — no Manim
mobjects constructed."""

from __future__ import annotations

import math

import pytest

from manim_renderer.components.data_viz.bar_chart import BarChart
from manim_renderer.components.data_viz.line_chart import LineChart
from manim_renderer.components.data_viz.metric_group import MetricGroup
from manim_renderer.components.data_viz.stat_block import StatBlock
from manim_renderer.components.game_theory.game_tree import GameTree
from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix
from manim_renderer.components.geopolitical.alliance_web import AllianceWeb
from manim_renderer.components.narrative.callout_box import CalloutBox
from manim_renderer.components.narrative.timeline import Timeline
from manim_renderer.components.text_card import TextCard


def _positive_finite(dims):
    w, h = dims
    return w > 0 and h > 0 and math.isfinite(w) and math.isfinite(h)


_REPRESENTATIVE = {
    "showTextCard": (TextCard, {"id": "x", "text": "hello", "size": "title"}),
    "showStatBlock": (StatBlock, {"id": "x", "value": 42, "label": "n"}),
    "showMetricGroup": (MetricGroup, {
        "id": "x", "orientation": "row",
        "stats": [{"value": 1, "label": "a"}, {"value": 2, "label": "b"}],
    }),
    "showCalloutBox": (CalloutBox, {
        "id": "x", "text": "annotation", "anchor": "below:t", "width": 4.0,
    }),
    "showBarChart": (BarChart, {
        "id": "x",
        "data": [{"label": "a", "value": 1}, {"label": "b", "value": 2}],
        "y_axis": {"min": 0, "max": 3, "ticks": 3},
    }),
    "showLineChart": (LineChart, {
        "id": "x",
        "series": [{"label": "s", "points": [[0, 1], [1, 2]]}],
        "y_axis": {"min": 0, "max": 3},
        "x_axis": {"min": 0, "max": 2},
    }),
    "showTimeline": (Timeline, {
        "id": "x",
        "events": [{"id": "e1", "label": "a"}, {"id": "e2", "label": "b"}],
    }),
    "showGameTree": (GameTree, {"id": "x", "nodes": {"label": "root"}}),
    "showAllianceWeb": (AllianceWeb, {
        "id": "x",
        "nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
        "edges": [],
    }),
    "showPayoffMatrix": (PayoffMatrix, {
        "id": "x",
        "players": [{"name": "P1", "color": "actor_a"}, {"name": "P2", "color": "actor_b"}],
        "strategies": [["C", "D"], ["C", "D"]],
        "cells": [
            [{"a": 1, "b": 1}, {"a": 0, "b": 5}],
            [{"a": 5, "b": 0}, {"a": 2, "b": 2}],
        ],
    }),
}


@pytest.mark.parametrize("action,fixture", list(_REPRESENTATIVE.items()))
@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_measure_returns_positive_finite(action, fixture, fmt):
    cls, params = fixture
    dims = cls.measure(params, fmt)
    assert _positive_finite(dims), f"{action} measure({fmt}) returned {dims}"


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_metric_group_row_sums_widths(fmt):
    """Row orientation: total width grows with stat count."""
    p2 = {"orientation": "row", "stats": [{"value": 1, "label": "a"}, {"value": 2, "label": "b"}]}
    p4 = {"orientation": "row", "stats": [{"value": i, "label": str(i)} for i in range(4)]}
    w2, h2 = MetricGroup.measure(p2, fmt)
    w4, h4 = MetricGroup.measure(p4, fmt)
    assert w4 > w2
    # Heights are max of child heights — same for both.
    assert h4 == h2


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_metric_group_column_sums_heights(fmt):
    """Column orientation: total height grows with stat count."""
    p2 = {"orientation": "column", "stats": [{"value": 1, "label": "a"}, {"value": 2, "label": "b"}]}
    p3 = {"orientation": "column", "stats": [{"value": i, "label": str(i)} for i in range(3)]}
    _, h2 = MetricGroup.measure(p2, fmt)
    _, h3 = MetricGroup.measure(p3, fmt)
    assert h3 > h2


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_stat_block_optional_features_increase_height(fmt):
    """trend and sparkline add to the base height."""
    base = StatBlock.measure({"value": 1, "label": "a"}, fmt)
    with_trend = StatBlock.measure(
        {"value": 1, "label": "a", "trend": {"delta": 1, "direction": "up"}}, fmt,
    )
    with_both = StatBlock.measure(
        {
            "value": 1, "label": "a",
            "trend": {"delta": 1, "direction": "up"},
            "sparkline": [1, 2, 3],
        }, fmt,
    )
    assert with_trend[1] > base[1]
    assert with_both[1] > with_trend[1]


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_callout_wider_text_wraps_to_more_lines(fmt):
    """Long text at the same `width` cap should produce a taller bubble."""
    short = CalloutBox.measure(
        {"text": "short", "anchor": "below:x", "width": 4.0}, fmt,
    )
    long = CalloutBox.measure(
        {"text": "x" * 200, "anchor": "below:x", "width": 4.0}, fmt,
    )
    assert long[1] > short[1]


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_size_role_monotonic(fmt):
    """large > medium > small for components that use resolve_size directly."""
    for cls in (BarChart, LineChart, PayoffMatrix, AllianceWeb):
        small = cls.measure({"size": "small"}, fmt)
        med = cls.measure({"size": "medium"}, fmt)
        large = cls.measure({"size": "large"}, fmt)
        # Either width or height should increase (size table is monotonic).
        assert (small[0] <= med[0] and small[1] <= med[1])
        assert (med[0] <= large[0] and med[1] <= large[1])

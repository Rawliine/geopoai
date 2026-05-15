"""PR H — `BaseComponent.preferred_size(params, format, role)`.

Two contracts:
  * Ordering: `hero > primary > supporting > ambient` for every component.
  * Hidden: returns `(0, 0)` exactly so the solver allocates no space.

Plus a unit test on the role-scale dict itself, since later PRs read it
directly when authoring solver allocations.
"""

from __future__ import annotations

import logging

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
from manim_renderer.layouts.base import ROLE_SCALE

logging.getLogger("manim").setLevel(logging.ERROR)


# Representative param dicts. Each must be a valid set for the matching
# component class's `measure()` (which is the default `preferred_size`'s
# base). Keep these aligned with `tests/components/test_measure.py`.
_FIXTURE_BY_CLS = {
    TextCard:      {"id": "x", "text": "hello"},
    StatBlock:     {"id": "x", "value": 1, "label": "L"},
    MetricGroup:   {
        "id": "x",
        "stats": [
            {"value": 1, "label": "A"},
            {"value": 2, "label": "B"},
        ],
    },
    BarChart:      {
        "id": "x",
        "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}],
    },
    LineChart:     {
        "id": "x",
        "series": [{"points": [[0, 0], [1, 1]]}],
    },
    Timeline:      {"id": "x", "events": [{"label": "E1"}]},
    GameTree:      {
        "id": "x",
        "nodes": {"label": "root", "children": [{"label": "leaf"}]},
    },
    AllianceWeb:   {
        "id": "x",
        "nodes": [{"id": "a"}, {"id": "b"}],
    },
    PayoffMatrix:  {
        "id": "x",
        "players": [{"name": "P1"}, {"name": "P2"}],
        "strategies": [["C", "D"], ["C", "D"]],
        "cells": [
            [{"a": 1, "b": 1}, {"a": 0, "b": 2}],
            [{"a": 2, "b": 0}, {"a": 1, "b": 1}],
        ],
    },
    CalloutBox:    {"id": "x", "text": "annotation", "anchor": "below:foo"},
}


# --- the scale dict itself ------------------------------------------------

def test_role_scale_contains_all_six_roles():
    assert set(ROLE_SCALE) == {
        "hero", "primary", "supporting", "ambient", "annotation", "hidden",
    }


def test_role_scale_hidden_is_zero():
    assert ROLE_SCALE["hidden"] == 0.0


def test_role_scale_strict_ordering():
    """The size ladder must be strict, otherwise the solver can produce
    rects that don't honor visual hierarchy."""
    assert ROLE_SCALE["hero"] > ROLE_SCALE["primary"] > ROLE_SCALE["supporting"] > ROLE_SCALE["ambient"]


# --- per-component preferred_size contract -------------------------------


@pytest.mark.parametrize("cls,params", list(_FIXTURE_BY_CLS.items()))
@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_hidden_returns_zero(cls, params, fmt):
    w, h = cls.preferred_size(params, fmt, "hidden")
    assert w == 0.0 and h == 0.0


@pytest.mark.parametrize("cls,params", list(_FIXTURE_BY_CLS.items()))
@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_role_size_strict_ordering(cls, params, fmt):
    h_w, h_h = cls.preferred_size(params, fmt, "hero")
    p_w, p_h = cls.preferred_size(params, fmt, "primary")
    s_w, s_h = cls.preferred_size(params, fmt, "supporting")
    a_w, a_h = cls.preferred_size(params, fmt, "ambient")
    assert h_w > p_w > s_w > a_w > 0
    assert h_h > p_h > s_h > a_h > 0


@pytest.mark.parametrize("cls,params", list(_FIXTURE_BY_CLS.items()))
@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_annotation_equals_primary(cls, params, fmt):
    """Annotations don't scale by role — their size is content-driven.
    Both should return base * 1.0 from the default linear scaling."""
    p_w, p_h = cls.preferred_size(params, fmt, "primary")
    a_w, a_h = cls.preferred_size(params, fmt, "annotation")
    assert p_w == pytest.approx(a_w)
    assert p_h == pytest.approx(a_h)


@pytest.mark.parametrize("cls,params", list(_FIXTURE_BY_CLS.items()))
def test_primary_equals_measure(cls, params):
    """The default linear-scale design says `primary` is the base unit.
    `preferred_size(.., 'primary')` must equal `measure(..)`."""
    m_w, m_h = cls.measure(params, "horizontal")
    p_w, p_h = cls.preferred_size(params, "horizontal", "primary")
    assert p_w == pytest.approx(m_w)
    assert p_h == pytest.approx(m_h)


# --- error paths ----------------------------------------------------------

def test_unknown_role_raises():
    with pytest.raises(ValueError, match="unknown role"):
        TextCard.preferred_size({"id": "x", "text": "hi"}, "horizontal", "vip")

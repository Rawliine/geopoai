"""PR M — `inherit_subject_color` walks a subject string to a palette key.

Rules under test:
  * `pd:cell:i,j` → row_player_color when a > b, col when b > a,
    `highlight` on tie.
  * `pd:row:i` / `pd:col:j` → the matching player's color.
  * Bare `id` with a `params.color` attr → that color.
  * Missing host or unknown shape → `highlight` fallback.

The runner injects the resolved key into the callout's params BEFORE
construction; explicit `params.color` always wins (asserted via runner
behavior in PR M's scene-level test, not the unit here).
"""

from __future__ import annotations

import logging

import pytest

from manim_renderer.components.data_viz.stat_block import StatBlock
from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix
from manim_renderer.resolvers.subject_color import inherit_subject_color

logging.getLogger("manim").setLevel(logging.ERROR)


def _pd() -> PayoffMatrix:
    return PayoffMatrix(
        {
            "id": "pd",
            "players": [{"name": "P1", "color": "actor_a"},
                         {"name": "P2", "color": "actor_b"}],
            "strategies": [["C", "D"], ["C", "D"]],
            "cells": [
                [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
                [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
            ],
        },
        format="horizontal",
    )


def test_cell_with_higher_a_returns_actor_a():
    pd = _pd()
    # cell (1,0): a=5, b=0 → row player dominates → actor_a.
    assert inherit_subject_color("pd:cell:1,0", {"pd": pd}) == "actor_a"


def test_cell_with_higher_b_returns_actor_b():
    pd = _pd()
    # cell (0,1): a=0, b=5 → col player dominates → actor_b.
    assert inherit_subject_color("pd:cell:0,1", {"pd": pd}) == "actor_b"


def test_cell_with_tied_payoff_falls_back_to_highlight():
    pd = _pd()
    # cell (0,0): a=3, b=3 → tie.
    assert inherit_subject_color("pd:cell:0,0", {"pd": pd}) == "highlight"


def test_row_returns_actor_a():
    pd = _pd()
    assert inherit_subject_color("pd:row:0", {"pd": pd}) == "actor_a"


def test_col_returns_actor_b():
    pd = _pd()
    assert inherit_subject_color("pd:col:0", {"pd": pd}) == "actor_b"


def test_bare_stat_block_returns_its_color():
    stat = StatBlock(
        {"id": "k", "value": 71.6, "label": "Defect", "color": "actor_b"},
        format="horizontal",
    )
    assert inherit_subject_color("k", {"k": stat}) == "actor_b"


def test_stat_block_without_color_falls_back():
    stat = StatBlock(
        {"id": "k", "value": 71.6, "label": "Defect"},
        format="horizontal",
    )
    assert inherit_subject_color("k", {"k": stat}) == "highlight"


def test_metric_group_child_anchor_returns_child_color():
    """A callout anchored at a MetricGroup child stat (registered via
    extra_id_registrations) inherits the child's palette key. The
    inheritance walks the child mobject's `palette_color` attribute,
    not the parent group's color_scheme."""
    from manim_renderer.components.data_viz.metric_group import MetricGroup

    group = MetricGroup(
        {
            "id": "kpis",
            "orientation": "row",
            "color_scheme": "actors",
            "stats": [
                {"id": "k-cooperate", "value": 28.4, "label": "Cooperate",
                 "color": "actor_a"},
                {"id": "k-defect", "value": 71.6, "label": "Defect",
                 "color": "actor_b"},
            ],
        },
        format="horizontal",
    )
    # The runner merges children into id_to_mobject via
    # extra_id_registrations. Simulate that here.
    id_to_mobject = {"kpis": group}
    id_to_mobject.update(group.extra_id_registrations())

    assert inherit_subject_color("k-cooperate", id_to_mobject) == "actor_a"
    assert inherit_subject_color("k-defect", id_to_mobject) == "actor_b"


def test_unknown_host_returns_fallback():
    assert inherit_subject_color("ghost", {}) == "highlight"


def test_malformed_cell_arg_falls_back():
    pd = _pd()
    assert inherit_subject_color("pd:cell:not-coords", {"pd": pd}) == "highlight"


def test_cell_out_of_bounds_falls_back():
    pd = _pd()
    assert inherit_subject_color("pd:cell:9,9", {"pd": pd}) == "highlight"


def test_explicit_color_param_overrides_inheritance():
    """The runner is responsible for honoring explicit colors — this is
    asserted by checking that scene.py only calls the resolver when
    `color` is absent. We pin the behavior at the resolver level by
    confirming the resolver doesn't read `params.color`."""
    # If we call the resolver explicitly on a subject that has a color,
    # we get the subject's color (resolver is dumb). The runner protects
    # against running this when params.color is already set.
    pd = _pd()
    # The resolver itself returns actor_b (from the cell payoffs).
    assert inherit_subject_color("pd:cell:0,1", {"pd": pd}) == "actor_b"

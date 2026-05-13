"""Schema-rejection tests for showLineChart."""

from __future__ import annotations

import copy

from manim_renderer.schema.validator import validate

_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {
        "main": {
            "at": 0.0,
            "action": "showLineChart",
            "params": {
                "id": "c",
                "series": [
                    {
                        "label": "USA",
                        "points": [[2010, 14], [2020, 21]],
                    }
                ],
            },
        }
    },
    "overlays": [],
    "timeline": [],
}


def _scene_with_params(params):
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"] = params
    return s


def test_minimum_passes():
    ok, errs = validate(_BASE)
    assert ok, errs


def test_missing_series_rejected():
    ok, errs = validate(_scene_with_params({"id": "c"}))
    assert not ok


def test_empty_series_rejected():
    ok, errs = validate(_scene_with_params({"id": "c", "series": []}))
    assert not ok


def test_single_point_series_rejected():
    bad = [{"label": "a", "points": [[0, 1]]}]
    ok, errs = validate(_scene_with_params({"id": "c", "series": bad}))
    assert not ok


def test_point_wrong_arity_rejected():
    """Points must be exactly [x, y] — two numbers."""
    bad = [{"label": "a", "points": [[0], [1, 1]]}]
    ok, errs = validate(_scene_with_params({"id": "c", "series": bad}))
    assert not ok


def test_point_extra_element_rejected():
    bad = [{"label": "a", "points": [[0, 0, 1], [1, 1]]}]
    ok, errs = validate(_scene_with_params({"id": "c", "series": bad}))
    assert not ok


def test_unknown_effect_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "series": [{
            "label": "a",
            "points": [[0, 0], [1, 1]],
        }],
        "effect": "count-up",  # not allowed on LineChart
    }))
    assert not ok


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "series": [
            {"label": "USA", "color": "actor_a",
             "points": [[2010, 14], [2020, 21]]},
            {"label": "China", "color": "actor_b",
             "points": [[2010, 6], [2020, 17]]},
        ],
        "size": "medium",
        "value_format": "decimal",
        "x_format": "int",
        "decimals": 1,
        "show_points": True,
        "x_axis": {"min": 2010, "max": 2020, "ticks": 6, "label": "Year"},
        "y_axis": {"min": 0, "max": 25, "ticks": 5, "label": "GDP ($T)"},
        "timing": "slow",
        "effect": "draw-out",
    }))
    assert ok, errs

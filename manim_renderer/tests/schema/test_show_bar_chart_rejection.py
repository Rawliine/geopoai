"""Schema-rejection tests for showBarChart."""

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
            "action": "showBarChart",
            "params": {
                "id": "c",
                "data": [
                    {"label": "USA", "value": 23000},
                    {"label": "China", "value": 17000},
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


def test_missing_data_rejected():
    ok, errs = validate(_scene_with_params({"id": "c"}))
    assert not ok
    assert any("data" in e for e in errs)


def test_empty_data_rejected():
    ok, errs = validate(_scene_with_params({"id": "c", "data": []}))
    assert not ok


def test_data_item_requires_label_and_value():
    ok, errs = validate(_scene_with_params({
        "id": "c", "data": [{"value": 1}],
    }))
    assert not ok
    assert any("label" in e for e in errs)


def test_data_item_rejects_extras():
    ok, errs = validate(_scene_with_params({
        "id": "c", "data": [{"label": "a", "value": 1, "wat": True}],
    }))
    assert not ok


def test_hex_color_in_data_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c", "data": [{"label": "a", "value": 1, "color": "#ff00ff"}],
    }))
    assert not ok


def test_unknown_color_role_in_data_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c", "data": [{"label": "a", "value": 1, "color": "puce"}],
    }))
    assert not ok


def test_unknown_effect_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "data": [{"label": "a", "value": 1}],
        "effect": "spiral-in",
    }))
    assert not ok


def test_y_axis_ticks_too_few_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "data": [{"label": "a", "value": 1}],
        "y_axis": {"ticks": 1},
    }))
    assert not ok


def test_y_axis_unknown_property_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "data": [{"label": "a", "value": 1}],
        "y_axis": {"wat": True},
    }))
    assert not ok


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "c",
        "data": [
            {"label": "USA", "value": 23000, "color": "actor_a"},
            {"label": "China", "value": 17000, "color": "actor_b"},
        ],
        "size": "medium",
        "value_format": "k",
        "decimals": 1,
        "show_value_labels": True,
        "y_axis": {"min": 0, "max": 25000, "ticks": 5, "label": "GDP ($B)"},
        "x_axis": {"label": "Country"},
        "timing": "slow",
        "effect": "count-up",
    }))
    assert ok, errs

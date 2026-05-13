"""Schema-rejection tests for showStatBlock."""

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
            "action": "showStatBlock",
            "params": {"id": "s", "value": 42, "label": "Defect"},
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


def test_missing_value_rejected():
    ok, errs = validate(_scene_with_params({"id": "s", "label": "x"}))
    assert not ok
    assert any("value" in e for e in errs)


def test_missing_label_rejected():
    ok, errs = validate(_scene_with_params({"id": "s", "value": 1}))
    assert not ok
    assert any("label" in e for e in errs)


def test_unknown_property_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "wat": True})
    )
    assert not ok
    assert any("wat" in e for e in errs)


def test_unknown_value_format_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "value_format": "lobster"})
    )
    assert not ok
    assert any("value_format" in e or "lobster" in e for e in errs)


def test_hex_color_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "color": "#ff00ff"})
    )
    assert not ok
    assert any("color" in e for e in errs)


def test_unknown_color_role_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "color": "puce"})
    )
    assert not ok
    assert any("color" in e or "puce" in e for e in errs)


def test_size_must_be_size_role():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "size": "title"})
    )
    assert not ok


def test_decimals_out_of_range_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "decimals": 99})
    )
    assert not ok


def test_trend_requires_delta_and_direction():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "trend": {"delta": 5}})
    )
    assert not ok
    assert any("direction" in e for e in errs)


def test_trend_unknown_direction_rejected():
    ok, errs = validate(
        _scene_with_params(
            {"id": "s", "value": 1, "label": "x",
             "trend": {"delta": 5, "direction": "sideways"}}
        )
    )
    assert not ok


def test_sparkline_too_short_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "sparkline": [5]})
    )
    assert not ok


def test_sparkline_non_numeric_rejected():
    ok, errs = validate(
        _scene_with_params({"id": "s", "value": 1, "label": "x", "sparkline": [1, "two", 3]})
    )
    assert not ok


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "s",
        "value": 1234567,
        "label": "GDP per capita",
        "value_format": "currency",
        "symbol": "$",
        "suffix": "auto",
        "decimals": 2,
        "color": "actor_a",
        "size": "large",
        "unit": "/y",
        "trend": {"delta": 12.3, "direction": "up", "color": "positive", "unit": "%"},
        "sparkline": [1, 2, 3, 4, 5, 6],
        "timing": "normal",
        "effect": "count-up",
    }))
    assert ok, errs

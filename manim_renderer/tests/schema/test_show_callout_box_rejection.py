"""Schema-rejection tests for showCalloutBox."""

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
            "action": "showTextCard",
            "params": {"id": "card", "text": "intro"},
        }
    },
    "overlays": [
        {
            "at": 1.0,
            "action": "showCalloutBox",
            "params": {"id": "cb", "text": "annotation", "anchor": "below:card"},
        }
    ],
    "timeline": [],
}


def _with_overlay_params(params):
    s = copy.deepcopy(_BASE)
    s["overlays"][0]["params"] = params
    return s


def test_minimum_passes():
    ok, errs = validate(_BASE)
    assert ok, errs


def test_missing_text_rejected():
    ok, errs = validate(_with_overlay_params({"id": "cb", "anchor": "below:card"}))
    assert not ok
    assert any("text" in e for e in errs)


def test_missing_anchor_rejected():
    ok, errs = validate(_with_overlay_params({"id": "cb", "text": "x"}))
    assert not ok
    assert any("anchor" in e for e in errs)


def test_anchor_without_token_rejected():
    ok, errs = validate(_with_overlay_params({"id": "cb", "text": "x", "anchor": "card"}))
    assert not ok


def test_anchor_unknown_token_rejected():
    ok, errs = validate(
        _with_overlay_params({"id": "cb", "text": "x", "anchor": "around:card"})
    )
    assert not ok


def test_anchor_target_must_exist():
    ok, errs = validate(
        _with_overlay_params({"id": "cb", "text": "x", "anchor": "below:ghost"})
    )
    assert not ok
    assert any("[anchor-target]" in e for e in errs)


def test_text_too_long_rejected():
    ok, errs = validate(
        _with_overlay_params({"id": "cb", "text": "x" * 500, "anchor": "below:card"})
    )
    assert not ok


def test_width_out_of_range_rejected():
    ok, errs = validate(
        _with_overlay_params({"id": "cb", "text": "x", "anchor": "below:card", "width": 12})
    )
    assert not ok


def test_full_featured_passes():
    ok, errs = validate(_with_overlay_params({
        "id": "cb",
        "text": "this is a callout",
        "anchor": "below:card",
        "width": 4.5,
        "arrow": True,
        "color": "highlight",
        "timing": "fast",
        "effect": "fade-in",
    }))
    assert ok, errs


def test_unknown_property_rejected():
    ok, errs = validate(
        _with_overlay_params(
            {"id": "cb", "text": "x", "anchor": "below:card", "rotation": 30}
        )
    )
    assert not ok
    assert any("rotation" in e for e in errs)

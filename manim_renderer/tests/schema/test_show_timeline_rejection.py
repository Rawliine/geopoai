"""Schema-rejection tests for showTimeline."""

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
            "action": "showTimeline",
            "params": {
                "id": "t",
                "events": [{"label": "x"}],
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


def test_missing_events_rejected():
    ok, errs = validate(_scene_with_params({"id": "t"}))
    assert not ok


def test_empty_events_rejected():
    ok, errs = validate(_scene_with_params({"id": "t", "events": []}))
    assert not ok


def test_event_missing_label_rejected():
    ok, errs = validate(_scene_with_params({"id": "t", "events": [{}]}))
    assert not ok
    assert any("label" in e for e in errs)


def test_event_extra_field_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t", "events": [{"label": "x", "wat": True}],
    }))
    assert not ok


def test_unknown_effect_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "events": [{"label": "x"}],
        "effect": "count-up",
    }))
    assert not ok


def test_max_visible_too_low_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "events": [{"label": "x"}],
        "max_visible": 1,
    }))
    assert not ok


def test_event_id_added_to_anchor_pool():
    """A callout anchored against an event's id should validate."""
    scene = copy.deepcopy(_BASE)
    scene["slots"]["main"]["params"] = {
        "id": "tl",
        "events": [
            {"id": "wwii", "label": "WWII"},
            {"id": "vj",   "label": "VJ Day"},
        ],
    }
    scene["overlays"] = [{
        "at": 2.0,
        "action": "showCalloutBox",
        "params": {
            "id": "callout",
            "text": "End of war",
            "anchor": "below:vj",
        },
    }]
    ok, errs = validate(scene)
    assert ok, errs


def test_duplicate_event_id_rejected():
    scene = copy.deepcopy(_BASE)
    scene["slots"]["main"]["params"] = {
        "id": "tl",
        "events": [
            {"id": "dup", "label": "A"},
            {"id": "dup", "label": "B"},
        ],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any("duplicate" in e for e in errs)


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "tl",
        "events": [
            {"id": "wwii", "at_label": "1939", "label": "WWII begins"},
            {"id": "vj",   "at_label": "1945", "label": "VJ Day", "color": "highlight"},
        ],
        "size": "large",
        "max_visible": 10,
        "timing": "slow",
        "effect": "level-by-level",
    }))
    assert ok, errs

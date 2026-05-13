"""Schema-rejection tests for showMetricGroup + child id extractor."""

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
            "action": "showMetricGroup",
            "params": {
                "id": "g",
                "stats": [
                    {"value": 1, "label": "A"},
                    {"value": 2, "label": "B"},
                ],
            },
        }
    },
    "overlays": [],
    "timeline": [],
}


def test_minimum_passes():
    ok, errs = validate(_BASE)
    assert ok, errs


def test_missing_stats_rejected():
    s = copy.deepcopy(_BASE)
    del s["slots"]["main"]["params"]["stats"]
    ok, errs = validate(s)
    assert not ok
    assert any("stats" in e for e in errs)


def test_single_stat_rejected_minItems_2():
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["stats"] = [{"value": 1, "label": "A"}]
    ok, errs = validate(s)
    assert not ok


def test_too_many_stats_rejected_maxItems_6():
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["stats"] = [
        {"value": i, "label": str(i)} for i in range(7)
    ]
    ok, errs = validate(s)
    assert not ok


def test_unknown_color_scheme_rejected():
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["color_scheme"] = "rainbow"
    ok, errs = validate(s)
    assert not ok


def test_orientation_enum_enforced():
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["orientation"] = "diagonal"
    ok, errs = validate(s)
    assert not ok


def test_child_id_collision_with_parent_caught_as_duplicate():
    """The id extractor exposes child stat ids; a collision with the parent's
    own id should fire the [semantic-id] duplicate check."""
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["stats"][0]["id"] = "g"  # same as parent
    ok, errs = validate(s)
    assert not ok
    assert any("[semantic-id]" in e and "'g'" in e for e in errs), errs


def test_child_id_collision_with_other_event_caught_as_duplicate():
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["stats"][0]["id"] = "stat-x"
    s["overlays"] = [{
        "at": 1.0,
        "action": "showTextCard",
        "params": {"id": "stat-x", "text": "boom"},
    }]
    ok, errs = validate(s)
    assert not ok
    assert any("[semantic-id]" in e and "stat-x" in e for e in errs), errs


def test_child_id_visible_to_anchor_target_check():
    """A callout pointing at an id declared as a child of MetricGroup should
    pass anchor validation (the id_extractor surfaces it to the validator)."""
    s = copy.deepcopy(_BASE)
    s["slots"]["main"]["params"]["stats"][0]["id"] = "k-a"
    s["slots"]["main"]["params"]["stats"][1]["id"] = "k-b"
    s["overlays"] = [{
        "at": 1.0,
        "action": "showCalloutBox",
        "params": {
            "id": "callout-1",
            "text": "look at A",
            "anchor": "right-of:k-a",
        },
    }]
    ok, errs = validate(s)
    assert ok, errs

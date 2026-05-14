"""Validator tier 5 — spatial dry-run checks (4a slot-fit, 4c anchor-overflow, 4b collision).

Exercises `manim_renderer/schema/_dry_run.py`. Each case is a minimal scene
that triggers exactly one error class.
"""

from __future__ import annotations

import copy

from manim_renderer.schema.validator import validate


# Minimal valid scene template — overridden per test.
_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {
        "main": {
            "at": 0.0,
            "action": "showTextCard",
            "params": {"id": "title", "text": "ok"},
        }
    },
    "overlays": [],
    "timeline": [],
}


def _scene(**overrides):
    s = copy.deepcopy(_BASE)
    for k, v in overrides.items():
        s[k] = v
    return s


# --- 4a slot-fit ----------------------------------------------------------


def test_slot_fit_oversize_metric_group_vertical():
    """3 medium StatBlocks stacked in vertical body slot — the bug that
    originally surfaced in `prisoners_dilemma_vertical.json`."""
    scene = {
        "renderer": "manim",
        "format": "vertical",
        "quality": "preview",
        "scene": {"layout": "title-body", "duration": 5},
        "slots": {
            "title": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "t", "text": "x", "size": "title"},
            },
            "body": {
                "at": 0.5,
                "action": "showMetricGroup",
                "params": {
                    "id": "kpis",
                    "orientation": "column",
                    "size": "medium",
                    "stats": [
                        {"value": 1, "label": "a", "trend": {"delta": 1, "direction": "up"}, "sparkline": [1, 2]},
                        {"value": 2, "label": "b", "trend": {"delta": 1, "direction": "up"}, "sparkline": [1, 2]},
                        {"value": 3, "label": "c", "trend": {"delta": 1, "direction": "up"}, "sparkline": [1, 2]},
                    ],
                },
            },
        },
        "overlays": [],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any("[layout-fit]" in e and "showMetricGroup" in e for e in errs), errs


def test_slot_fit_small_metric_group_vertical_passes():
    """Same shape with size:small fits."""
    scene = {
        "renderer": "manim",
        "format": "vertical",
        "quality": "preview",
        "scene": {"layout": "title-body", "duration": 5},
        "slots": {
            "title": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "t", "text": "x", "size": "title"},
            },
            "body": {
                "at": 0.5,
                "action": "showMetricGroup",
                "params": {
                    "id": "kpis",
                    "orientation": "column",
                    "size": "small",
                    "stats": [
                        {"value": 1, "label": "a"},
                        {"value": 2, "label": "b"},
                        {"value": 3, "label": "c"},
                    ],
                },
            },
        },
        "overlays": [],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert ok, errs


# --- 4c anchor-overflow ---------------------------------------------------


def test_anchor_overflow_below_bottom_of_frame():
    """A callout anchored below a component near the bottom of the frame
    should overflow."""
    # Put a component near the bottom by anchoring it below the title slot
    # in a tight layout. Use a wide chart in hero so a below callout falls
    # off frame.
    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 5},
        "slots": {
            "main": {
                "at": 0.0,
                "action": "showBarChart",
                "params": {
                    "id": "chart",
                    "size": "large",
                    "data": [{"label": "a", "value": 1}, {"label": "b", "value": 2}],
                    "y_axis": {"min": 0, "max": 3, "ticks": 3},
                },
            }
        },
        "overlays": [
            {
                "at": 1.0,
                "action": "showCalloutBox",
                "params": {
                    "id": "cb",
                    "text": "x" * 200,
                    "anchor": "below:chart",
                    "width": 6.0,
                },
            }
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any("[anchor-overflow]" in e or "[frame-overflow]" in e for e in errs), errs


# --- 4b collision ---------------------------------------------------------


def test_collision_two_slot_components_dont_overlap():
    """Components placed in disjoint slots should not trigger collision."""
    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "split", "duration": 5},
        "slots": {
            "left": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "a", "text": "left"},
            },
            "right": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "b", "text": "right"},
            },
        },
        "overlays": [],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert ok, errs


def test_collision_anchored_into_slot_component_flagged():
    """A new component anchored into the same space as an existing slot
    component overlaps and should be flagged."""
    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "split", "duration": 5},
        "slots": {
            "left": {
                "at": 0.0,
                "action": "showPayoffMatrix",
                "params": {
                    "id": "pd",
                    "size": "medium",
                    "players": [
                        {"name": "P1", "color": "actor_a"},
                        {"name": "P2", "color": "actor_b"},
                    ],
                    "strategies": [["C", "D"], ["C", "D"]],
                    "cells": [
                        [{"a": 1, "b": 1}, {"a": 0, "b": 5}],
                        [{"a": 5, "b": 0}, {"a": 2, "b": 2}],
                    ],
                },
            },
            "right": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "rt", "text": "r"},
            },
        },
        "overlays": [
            # A second matrix anchored right-of pd lands in the right slot.
            {
                "at": 1.0,
                "action": "showPayoffMatrix",
                "params": {
                    "id": "pd2",
                    "size": "medium",
                    "anchor": "right-of:pd",
                    "players": [
                        {"name": "P1", "color": "actor_a"},
                        {"name": "P2", "color": "actor_b"},
                    ],
                    "strategies": [["C", "D"], ["C", "D"]],
                    "cells": [
                        [{"a": 1, "b": 1}, {"a": 0, "b": 5}],
                        [{"a": 5, "b": 0}, {"a": 2, "b": 2}],
                    ],
                },
            }
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any("[collision-overlap]" in e or "[anchor-overflow]" in e for e in errs), errs


def test_removed_components_dropped_from_cast():
    """After removeComponent, the id should not trigger collision against
    a later overlay placed inside its old position. Uses CalloutBox (which
    accepts `anchor`) and `inside:` (which is also skipped from collision
    checks by intent — verifies the two behaviors compose)."""
    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 10},
        "slots": {
            "main": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "first", "text": "a"},
            }
        },
        "overlays": [
            {
                "at": 2.0,
                "action": "removeComponent",
                "params": {"target": "first", "effect": "fade-out"},
            },
            {
                "at": 3.0,
                "action": "showCalloutBox",
                "params": {
                    "id": "second", "text": "b",
                    "anchor": "inside:first", "width": 2.0,
                },
            },
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert ok, errs

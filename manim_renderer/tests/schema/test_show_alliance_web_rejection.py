"""Schema-rejection tests for showAllianceWeb."""

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
            "action": "showAllianceWeb",
            "params": {
                "id": "w",
                "nodes": [
                    {"id": "usa", "label": "USA"},
                    {"id": "rus", "label": "Russia"},
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


def test_too_few_nodes_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "w", "nodes": [{"id": "solo"}],
    }))
    assert not ok


def test_node_missing_id_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "w", "nodes": [{"label": "x"}, {"id": "y"}],
    }))
    assert not ok


def test_edge_unknown_kind_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "w",
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b", "kind": "trade"}],
    }))
    assert not ok


def test_unknown_effect_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "w",
        "nodes": [{"id": "a"}, {"id": "b"}],
        "effect": "count-up",
    }))
    assert not ok


def test_node_ids_exposed_for_anchor_resolution():
    """A callout anchored at `below:usa` should validate when usa is a node id."""
    scene = copy.deepcopy(_BASE)
    scene["overlays"] = [{
        "at": 2.0,
        "action": "showCalloutBox",
        "params": {
            "id": "callout",
            "text": "Power broker",
            "anchor": "below:usa",
        },
    }]
    ok, errs = validate(scene)
    assert ok, errs


def test_duplicate_node_id_rejected():
    """Node ids participate in the validator's duplicate-id check."""
    scene = copy.deepcopy(_BASE)
    scene["slots"]["main"]["params"] = {
        "id": "w",
        "nodes": [{"id": "dup"}, {"id": "dup"}],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any("duplicate" in e for e in errs)


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "w",
        "nodes": [
            {"id": "usa", "label": "USA", "color": "actor_a"},
            {"id": "rus", "label": "Russia", "color": "actor_b"},
            {"id": "chn", "label": "China", "color": "actor_c"},
        ],
        "edges": [
            {"from": "usa", "to": "rus", "kind": "rivalry"},
            {"from": "rus", "to": "chn", "kind": "alliance"},
            {"from": "usa", "to": "chn", "kind": "neutral"},
        ],
        "size": "medium",
        "seed": 7,
        "timing": "slow",
        "effect": "level-by-level",
    }))
    assert ok, errs

"""Schema-rejection tests for showGameTree."""

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
            "action": "showGameTree",
            "params": {
                "id": "t",
                "nodes": {"label": "root"},
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


def test_missing_nodes_rejected():
    ok, errs = validate(_scene_with_params({"id": "t"}))
    assert not ok


def test_node_missing_label_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "nodes": {"children": [{"label": "x"}]},
    }))
    assert not ok


def test_child_extra_field_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "nodes": {"label": "root", "children": [{"label": "x", "wat": True}]},
    }))
    assert not ok


def test_deeply_nested_children_validate():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "nodes": {
            "label": "L1",
            "children": [
                {"label": "L2", "children": [
                    {"label": "L3", "children": [
                        {"label": "L4"}
                    ]}
                ]}
            ],
        },
    }))
    assert ok, errs


def test_unknown_effect_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t", "nodes": {"label": "root"}, "effect": "draw-out",
    }))
    assert not ok


def test_max_depth_too_low_rejected():
    ok, errs = validate(_scene_with_params({
        "id": "t", "nodes": {"label": "root"}, "max_depth": 1,
    }))
    assert not ok


def test_full_featured_passes():
    ok, errs = validate(_scene_with_params({
        "id": "t",
        "nodes": {
            "label": "P1",
            "color": "actor_a",
            "children": [
                {"label": "C", "edge": "C", "children": [
                    {"label": "(3,3)", "edge": "C"},
                    {"label": "(0,5)", "edge": "D"},
                ]},
                {"label": "D", "edge": "D"},
            ],
        },
        "size": "large",
        "max_depth": 4,
        "timing": "slow",
        "effect": "level-by-level",
    }))
    assert ok, errs

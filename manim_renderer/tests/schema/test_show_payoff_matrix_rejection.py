"""Schema-rejection tests for showPayoffMatrix."""

from __future__ import annotations

import copy

from manim_renderer.schema.validator import validate

_PARAMS = {
    "id": "m",
    "players": [{"name": "P1"}, {"name": "P2"}],
    "strategies": [["C", "D"], ["C", "D"]],
    "cells": [
        [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
        [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
    ],
}

_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {
        "main": {
            "at": 0.0,
            "action": "showPayoffMatrix",
            "params": _PARAMS,
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


def test_missing_cells_rejected():
    p = copy.deepcopy(_PARAMS)
    del p["cells"]
    ok, errs = validate(_scene_with_params(p))
    assert not ok


def test_wrong_player_count_rejected():
    p = copy.deepcopy(_PARAMS)
    p["players"] = [{"name": "P1"}]
    ok, errs = validate(_scene_with_params(p))
    assert not ok


def test_cell_missing_b_rejected():
    p = copy.deepcopy(_PARAMS)
    p["cells"][0][0] = {"a": 1}
    ok, errs = validate(_scene_with_params(p))
    assert not ok


def test_unknown_effect_rejected():
    p = copy.deepcopy(_PARAMS)
    p["effect"] = "count-up"
    ok, errs = validate(_scene_with_params(p))
    assert not ok


def test_full_featured_passes():
    p = copy.deepcopy(_PARAMS)
    p["players"] = [{"name": "P1", "color": "actor_a"},
                     {"name": "P2", "color": "actor_b"}]
    p["size"] = "large"
    p["timing"] = "slow"
    p["effect"] = "level-by-level"
    ok, errs = validate(_scene_with_params(p))
    assert ok, errs

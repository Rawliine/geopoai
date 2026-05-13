"""Schema-rejection tests for the PayoffMatrix mutation actions:
highlightCell / crossOut / bestResponseArrow.
"""

from __future__ import annotations

import copy

from manim_renderer.schema.validator import validate


def _scene_with_matrix_and_overlay(overlay_event):
    return {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 5},
        "slots": {
            "main": {
                "at": 0.0,
                "action": "showPayoffMatrix",
                "params": {
                    "id": "m",
                    "players": [{"name": "P1"}, {"name": "P2"}],
                    "strategies": [["C", "D"], ["C", "D"]],
                    "cells": [
                        [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
                        [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
                    ],
                },
            }
        },
        "overlays": [overlay_event],
        "timeline": [],
    }


# --- highlightCell ---------------------------------------------------------

def test_highlight_cell_passes():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"target": "m", "index": [1, 1], "color": "highlight"},
    }))
    assert ok, errs


def test_highlight_cell_missing_target():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"index": [0, 0]},
    }))
    assert not ok


def test_highlight_cell_missing_index():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"target": "m"},
    }))
    assert not ok


def test_highlight_cell_bad_index_shape():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"target": "m", "index": [0, 0, 0]},
    }))
    assert not ok


def test_highlight_cell_unknown_color_rejected():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"target": "m", "index": [0, 0], "color": "puce"},
    }))
    assert not ok


def test_highlight_cell_target_must_exist():
    """validator's id-ref check fires when `target` doesn't reference a
    previously-declared id."""
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "highlightCell",
        "params": {"target": "nope", "index": [0, 0]},
    }))
    assert not ok
    assert any("id" in e for e in errs)


# --- crossOut --------------------------------------------------------------

def test_cross_out_passes():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "crossOut",
        "params": {"target": "m", "axis": "row", "index": 0, "style": "strike"},
    }))
    assert ok, errs


def test_cross_out_bad_axis():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "crossOut",
        "params": {"target": "m", "axis": "diagonal", "index": 0},
    }))
    assert not ok


def test_cross_out_bad_style():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "crossOut",
        "params": {"target": "m", "axis": "row", "index": 0, "style": "wavy"},
    }))
    assert not ok


# --- bestResponseArrow ----------------------------------------------------

def test_best_response_arrow_passes():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "bestResponseArrow",
        "params": {
            "target": "m", "from": [0, 0], "to": [0, 1], "actor": "actor_a",
        },
    }))
    assert ok, errs


def test_best_response_arrow_missing_actor():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "bestResponseArrow",
        "params": {"target": "m", "from": [0, 0], "to": [0, 1]},
    }))
    assert not ok


def test_best_response_arrow_bad_coord_shape():
    ok, errs = validate(_scene_with_matrix_and_overlay({
        "at": 2.0, "action": "bestResponseArrow",
        "params": {
            "target": "m", "from": [0], "to": [0, 1], "actor": "actor_a",
        },
    }))
    assert not ok

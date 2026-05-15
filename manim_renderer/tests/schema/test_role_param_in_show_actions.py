"""Every component schema must accept the optional `role` param (PR F).

Two-layer check:
  1. Static: each `show_*.json` schema declares `role` under `properties` and
     `$ref`s the centralized definition.
  2. Live: validating a minimal scene that includes `role` in the params
     succeeds; an unknown role fails.

Adding a new show_* action means appending a fixture here. The static check
catches the forgotten enum entry on its own.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from manim_renderer.schema.validator import validate

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema" / "action_schemas"

# Every component action shipped through Phase 1. Keep this in sync with
# manim_renderer/registry.py:COMPONENT_REGISTRY.
_COMPONENT_ACTIONS = [
    "showTextCard",
    "showStatBlock",
    "showMetricGroup",
    "showCalloutBox",
    "showBarChart",
    "showLineChart",
    "showTimeline",
    "showGameTree",
    "showAllianceWeb",
    "showPayoffMatrix",
]


def _camel_to_snake(name: str) -> str:
    return "".join(("_" + c.lower()) if c.isupper() else c for c in name).lstrip("_")


def _schema_for(action: str) -> dict:
    path = _SCHEMA_DIR / f"{_camel_to_snake(action)}.json"
    with path.open() as f:
        return json.load(f)


@pytest.mark.parametrize("action", _COMPONENT_ACTIONS)
def test_role_is_declared_in_schema(action):
    schema = _schema_for(action)
    properties = schema.get("properties", {})
    assert "role" in properties, (
        f"{action}.params schema is missing 'role'; "
        f"declared keys: {sorted(properties)}"
    )
    # The $ref must point at the centralized role_name enum so adding a new
    # role value requires one edit (not 10).
    expected_ref = "../scene_schema.json#/definitions/role_name"
    assert properties["role"].get("$ref") == expected_ref, (
        f"{action}.role should $ref {expected_ref!r}, "
        f"got {properties['role']!r}"
    )


# --- live validation pass + fail per component ----------------------------

# Minimum valid params for each component. Mirrors how the QA scenes wire
# things up but pared to the smallest set that satisfies each schema.
_VALID_PARAMS_FOR: dict[str, dict] = {
    "showTextCard": {"id": "x", "text": "hello"},
    "showStatBlock": {"id": "x", "value": 1, "label": "L"},
    "showMetricGroup": {
        "id": "x",
        "stats": [
            {"value": 1, "label": "A"},
            {"value": 2, "label": "B"},
        ],
    },
    "showBarChart": {
        "id": "x",
        "data": [{"label": "A", "value": 1}],
    },
    "showLineChart": {
        "id": "x",
        "series": [{"points": [[0, 0], [1, 1]]}],
    },
    "showTimeline": {
        "id": "x",
        "events": [{"label": "E1"}],
    },
    "showGameTree": {
        "id": "x",
        "nodes": {"label": "root", "children": [{"label": "leaf"}]},
    },
    "showAllianceWeb": {
        "id": "x",
        "nodes": [{"id": "a"}, {"id": "b"}],
    },
    "showPayoffMatrix": {
        "id": "x",
        "players": [{"name": "P1"}, {"name": "P2"}],
        "strategies": [["C", "D"], ["C", "D"]],
        "cells": [
            [{"a": 1, "b": 1}, {"a": 0, "b": 2}],
            [{"a": 2, "b": 0}, {"a": 1, "b": 1}],
        ],
    },
}

# CalloutBox needs an anchor, so it lives in overlays referencing a prior id.


def _scene_with_slot(action: str, params: dict) -> dict:
    return {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 10},
        "slots": {"main": {"at": 0.0, "action": action, "params": params}},
        "overlays": [],
        "timeline": [],
    }


def _scene_with_callout_overlay(callout_params: dict) -> dict:
    return {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 10},
        "slots": {
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "card", "text": "hi"}},
        },
        "overlays": [
            {"at": 1.0, "action": "showCalloutBox", "params": callout_params}
        ],
        "timeline": [],
    }


@pytest.mark.parametrize("action", list(_VALID_PARAMS_FOR.keys()))
def test_role_accepted_on_show_actions(action):
    params = {**_VALID_PARAMS_FOR[action], "role": "supporting"}
    scene = _scene_with_slot(action, params)
    ok, errs = validate(scene)
    assert ok, (action, errs)


def test_role_accepted_on_show_callout_box():
    params = {"id": "cb", "text": "x", "anchor": "below:card", "role": "annotation"}
    scene = _scene_with_callout_overlay(params)
    ok, errs = validate(scene)
    assert ok, errs


@pytest.mark.parametrize("action", list(_VALID_PARAMS_FOR.keys()))
def test_unknown_role_rejected_on_show_actions(action):
    params = {**_VALID_PARAMS_FOR[action], "role": "vip"}
    scene = _scene_with_slot(action, params)
    ok, errs = validate(scene)
    assert not ok
    assert any("role" in e and "[action-params]" in e for e in errs), (action, errs)


def test_unknown_role_rejected_on_show_callout_box():
    params = {"id": "cb", "text": "x", "anchor": "below:card", "role": "vip"}
    scene = _scene_with_callout_overlay(params)
    ok, errs = validate(scene)
    assert not ok
    assert any("role" in e and "[action-params]" in e for e in errs), errs


def test_role_optional_default_validates():
    """No `role` key still validates — the param is purely optional."""
    scene = _scene_with_slot("showTextCard", {"id": "x", "text": "hi"})
    ok, errs = validate(scene)
    assert ok, errs


def test_known_action_list_matches_schema_files():
    """Sanity: every `show_*.json` schema (excluding action-shaped ones like
    `show_callout_sequence`) corresponds to a registered COMPONENT_REGISTRY
    entry. If a new show_*.json lands without an entry here, the test forces
    an update."""
    # `show_callout_sequence.json` lives in the same folder but is an action
    # schema (registered in ACTION_REGISTRY, not COMPONENT_REGISTRY). Filter
    # it out to keep the assertion targeted at components.
    on_disk = sorted(
        p.stem for p in _SCHEMA_DIR.glob("show_*.json")
        if p.stem != "show_callout_sequence"
    )
    expected = sorted(_camel_to_snake(a) for a in _COMPONENT_ACTIONS)
    assert on_disk == expected, (on_disk, expected)

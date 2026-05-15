"""Schema rejection tests for `setLayout`."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import referencing

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
_ACTION_SCHEMA = json.loads(
    (_SCHEMA_DIR / "action_schemas" / "set_layout.json").read_text()
)
_SCENE_SCHEMA = json.loads((_SCHEMA_DIR / "scene_schema.json").read_text())


def _registry() -> referencing.Registry:
    scene_resource = referencing.Resource.from_contents(_SCENE_SCHEMA)
    return referencing.Registry().with_resources([
        ("../scene_schema.json", scene_resource),
        ("scene_schema.json", scene_resource),
    ])


def _validate(params: dict):
    jsonschema.Draft7Validator(_ACTION_SCHEMA, registry=_registry()).validate(params)


def test_minimal_params_accepted():
    _validate({"layout": "split"})


def test_with_timing_accepted():
    _validate({"layout": "trio", "timing": "normal"})


def test_unknown_layout_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate({"layout": "not-a-layout"})


def test_missing_layout_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate({})


def test_extra_property_rejected():
    with pytest.raises(jsonschema.ValidationError):
        _validate({"layout": "hero", "extra": "nope"})

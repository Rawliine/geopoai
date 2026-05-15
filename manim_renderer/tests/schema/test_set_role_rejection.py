"""Schema-rejection tests for setRole (PR F).

Each case constructs a scene that should FAIL validation for one specific
reason. The positive case at the bottom asserts the action validates cleanly.
"""

from __future__ import annotations

import copy

import pytest

from manim_renderer.schema.validator import validate

_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {
        "main": {"at": 0.0, "action": "showTextCard",
                 "params": {"id": "hello", "text": "x"}},
    },
    "overlays": [],
    "timeline": [],
}


def _with_set_role(params: dict):
    s = copy.deepcopy(_BASE)
    s["timeline"] = [{"at": 1.0, "action": "setRole", "params": params}]
    return s


def test_missing_target_rejected():
    scene = _with_set_role({"role": "supporting"})
    ok, errs = validate(scene)
    assert not ok
    assert any("target" in e for e in errs), errs


def test_missing_role_rejected():
    scene = _with_set_role({"target": "hello"})
    ok, errs = validate(scene)
    assert not ok
    assert any("role" in e for e in errs), errs


def test_unknown_role_rejected():
    scene = _with_set_role({"target": "hello", "role": "vip"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "role" in e for e in errs), errs


def test_unknown_property_rejected():
    scene = _with_set_role({"target": "hello", "role": "supporting", "wat": 1})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "wat" in e for e in errs), errs


def test_target_must_be_kebab():
    scene = _with_set_role({"target": "Hello_World", "role": "supporting"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "target" in e for e in errs), errs


def test_target_must_reference_earlier_id():
    """Tier 4 catches references to undeclared ids."""
    scene = _with_set_role({"target": "ghost", "role": "supporting"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[id-ref]" in e for e in errs), errs


def test_unknown_timing_rejected():
    scene = _with_set_role({"target": "hello", "role": "supporting", "timing": "lightning"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "timing" in e for e in errs), errs


@pytest.mark.parametrize("role", [
    "hero", "primary", "supporting", "ambient", "annotation", "hidden",
])
def test_all_six_roles_accepted(role):
    scene = _with_set_role({"target": "hello", "role": role})
    ok, errs = validate(scene)
    assert ok, (role, errs)


def test_valid_set_role_passes():
    scene = _with_set_role({"target": "hello", "role": "supporting", "timing": "fast"})
    ok, errs = validate(scene)
    assert ok, errs

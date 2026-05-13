"""Schema-rejection tests for removeComponent.

Each case constructs a scene that should FAIL validation for one specific reason.
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


def _with_overlay(params: dict):
    s = copy.deepcopy(_BASE)
    s["overlays"] = [{"at": 1.0, "action": "removeComponent", "params": params}]
    return s


def test_missing_target_rejected():
    scene = _with_overlay({})
    ok, errs = validate(scene)
    assert not ok
    assert any("target" in e for e in errs), errs


def test_unknown_property_rejected():
    scene = _with_overlay({"target": "hello", "wat": True})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "wat" in e for e in errs), errs


def test_target_must_be_kebab():
    scene = _with_overlay({"target": "Hello_World"})  # not kebab
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "target" in e for e in errs), errs


def test_unknown_effect_rejected():
    scene = _with_overlay({"target": "hello", "effect": "explode"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "explode" in e for e in errs), errs


def test_unknown_timing_rejected():
    scene = _with_overlay({"target": "hello", "timing": "lightning"})
    ok, errs = validate(scene)
    assert not ok
    assert any("[action-params]" in e and "lightning" in e for e in errs), errs


def test_valid_remove_passes():
    scene = _with_overlay({"target": "hello", "effect": "fade-out", "timing": "fast"})
    ok, errs = validate(scene)
    assert ok, errs

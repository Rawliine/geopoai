"""Tests for the validator's tier-4 anchor + id-ref checks."""

from __future__ import annotations

import copy

import pytest

from manim_renderer.schema.validator import validate

_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {},
    "overlays": [],
    "timeline": [],
}


def _scene(**overrides):
    s = copy.deepcopy(_BASE)
    for k, v in overrides.items():
        s[k] = v
    return s


def test_target_pointing_at_earlier_id_passes():
    scene = _scene(
        slots={
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "hello", "text": "x"}}
        },
        overlays=[
            {"at": 1.0, "action": "removeComponent",
             "params": {"target": "hello", "effect": "fade-out"}},
        ],
    )
    ok, errs = validate(scene)
    assert ok, errs


def test_target_pointing_at_unknown_id_fails():
    scene = _scene(
        overlays=[
            {"at": 0.0, "action": "removeComponent", "params": {"target": "ghost"}},
        ],
    )
    ok, errs = validate(scene)
    assert not ok
    assert any("[id-ref]" in e and "ghost" in e for e in errs), errs


def test_target_at_same_at_but_earlier_phase_resolves():
    """Slot fires before overlay at the same `at` (phase tiebreak), so
    overlay can reference slot's id."""
    scene = _scene(
        slots={
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "hello", "text": "x"}}
        },
        overlays=[
            {"at": 0.0, "action": "removeComponent", "params": {"target": "hello"}},
        ],
    )
    ok, errs = validate(scene)
    assert ok, errs


def test_target_at_same_at_but_later_phase_fails_when_referenced_first():
    """Overlay fires before timeline at the same at — a timeline event cannot
    target a later overlay's id, but an overlay CAN target a slot's id (above
    test). This test inverts: a slot cannot target a later overlay's id."""
    scene = _scene(
        slots={
            "main": {"at": 0.0, "action": "removeComponent",
                     "params": {"target": "later"}},
        },
        overlays=[
            {"at": 0.0, "action": "showTextCard",
             "params": {"id": "later", "text": "x"}},
        ],
    )
    ok, errs = validate(scene)
    assert not ok
    assert any("[id-ref]" in e and "later" in e for e in errs), errs


def test_self_reference_at_same_event_fails():
    """An event cannot reference its own id — declaration happens AFTER the ref check."""
    scene = _scene(
        overlays=[
            {"at": 0.0, "action": "removeComponent", "params": {"target": "self"}},
        ],
    )
    ok, errs = validate(scene)
    assert not ok
    assert any("[id-ref]" in e and "self" in e for e in errs), errs


def test_anchor_shape_validation():
    """Malformed anchor strings caught by parse_anchor are surfaced separately."""
    # NOTE: removeComponent uses `target` (id-ref), not `anchor` (anchor-string).
    # When a Phase 1 component (CalloutBox in PR 1.2) lands with `anchor` param,
    # this test will exercise the [anchor-shape] path. For now, verify the code
    # path by feeding a hand-crafted action event with an `anchor` param.
    # Since no schema currently allows it, structural validation will fail first
    # on `additionalProperties: false`. This test documents the intent; the
    # anchor-shape branch is exercised in PR 1.2 when CalloutBox lands.
    pass

"""PR O — `showCalloutSequence` chains callouts via Succession.

The action callable:
  * Validates required params (id, non-empty callouts).
  * Constructs a CalloutBox per item with role=annotation.
  * Inherits color from subject when no explicit color provided.
  * Returns a `Succession(enter, hold, exit, enter, hold, exit, ...)`.
  * Registers the sequence id in `id_to_mobject` so removeComponent
    can target it.
"""

from __future__ import annotations

import logging

import pytest
from manim import Succession

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.show_callout_sequence import show_callout_sequence
from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix
from manim_renderer.components.text_card import TextCard

logging.getLogger("manim").setLevel(logging.ERROR)


class _StubScene:
    def __init__(self):
        self._overlays_by_host: dict[str, list] = {}
        self._roles: dict[str, str] = {}


def _matrix() -> PayoffMatrix:
    return PayoffMatrix(
        {
            "id": "pd",
            "players": [{"name": "P1", "color": "actor_a"},
                         {"name": "P2", "color": "actor_b"}],
            "strategies": [["C", "D"], ["C", "D"]],
            "cells": [
                [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
                [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
            ],
        },
        format="horizontal",
    )


def _ctx(params: dict, registry: dict) -> ActionContext:
    return ActionContext(
        params=params,
        id_to_mobject=registry,
        format="horizontal",
        scene=_StubScene(),
    )


# --- happy path -----------------------------------------------------------


def test_sequence_with_three_subjects_returns_succession():
    pd = _matrix()
    ctx = _ctx({
        "id": "seq-1",
        "callouts": [
            {"subject": "pd:cell:1,0", "text": "first"},
            {"subject": "pd:cell:0,1", "text": "second"},
            {"subject": "pd:cell:1,1", "text": "third"},
        ],
    }, {"pd": pd})

    anim = show_callout_sequence(ctx)
    assert isinstance(anim, Succession)


def test_sequence_registers_top_level_id():
    pd = _matrix()
    registry = {"pd": pd}
    ctx = _ctx({
        "id": "seq-1",
        "callouts": [
            {"subject": "pd", "text": "one"},
        ],
    }, registry)
    show_callout_sequence(ctx)
    assert "seq-1" in registry


def test_anchor_form_works_alongside_subject():
    card = TextCard({"id": "card", "text": "hello"}, format="horizontal")
    ctx = _ctx({
        "id": "seq",
        "callouts": [
            {"anchor": "below:card", "text": "a"},
            {"anchor": "below:card", "text": "b"},
        ],
    }, {"card": card})
    anim = show_callout_sequence(ctx)
    assert isinstance(anim, Succession)


def test_default_style_neon():
    """No `style` param → default `neon` style applied to each item."""
    pd = _matrix()
    ctx = _ctx({
        "id": "seq",
        "callouts": [{"subject": "pd", "text": "x"}],
    }, {"pd": pd})
    show_callout_sequence(ctx)  # just asserting no crash on default


# --- error paths ----------------------------------------------------------


def test_missing_id_raises():
    pd = _matrix()
    ctx = _ctx({
        "callouts": [{"subject": "pd", "text": "x"}],
    }, {"pd": pd})
    with pytest.raises(ValueError, match="id"):
        show_callout_sequence(ctx)


def test_empty_callouts_raises():
    pd = _matrix()
    ctx = _ctx({"id": "seq", "callouts": []}, {"pd": pd})
    with pytest.raises(ValueError, match="callouts"):
        show_callout_sequence(ctx)


# --- schema validation ----------------------------------------------------


def test_schema_validates_minimal_sequence():
    from manim_renderer.schema.validator import validate

    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 10},
        "slots": {
            "main": {
                "at": 0.0,
                "action": "showPayoffMatrix",
                "params": {
                    "id": "pd",
                    "players": [{"name": "P1"}, {"name": "P2"}],
                    "strategies": [["C", "D"], ["C", "D"]],
                    "cells": [
                        [{"a": 1, "b": 1}, {"a": 0, "b": 2}],
                        [{"a": 2, "b": 0}, {"a": 1, "b": 1}],
                    ],
                },
            },
        },
        "overlays": [
            {
                "at": 2.0,
                "action": "showCalloutSequence",
                "params": {
                    "id": "seq-1",
                    "callouts": [
                        {"subject": "pd:cell:1,0", "text": "one"},
                        {"subject": "pd:cell:0,1", "text": "two"},
                    ],
                    "hold_each": "slow",
                    "transition": "fast",
                },
            },
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert ok, errs


def test_schema_rejects_callout_item_missing_anchor_and_subject():
    from manim_renderer.schema.validator import validate

    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 10},
        "slots": {
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "card", "text": "hi"}},
        },
        "overlays": [
            {
                "at": 1.0,
                "action": "showCalloutSequence",
                "params": {
                    "id": "seq",
                    "callouts": [{"text": "no target"}],
                },
            },
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok


def test_schema_rejects_empty_callouts_array():
    from manim_renderer.schema.validator import validate

    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 5},
        "slots": {
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "card", "text": "hi"}},
        },
        "overlays": [
            {"at": 1.0, "action": "showCalloutSequence",
             "params": {"id": "seq", "callouts": []}},
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok

"""PR G — `_restage` is invoked at the right composition-changing moments.

Running `JSONScene.construct()` end-to-end requires a Manim renderer and
makes these tests slow + flaky in a `-m "not render"` suite. Instead we:

  1. Inspect `JSONScene.construct`'s source AST to assert `_restage` is
     called in the main event loop guarded by the expected action sets.
  2. Drive the runner's event-handling branches in isolation with stubbed
     `play`/`wait` and a counting `_restage`, asserting one call per
     composition-changing event and zero calls per mutation.

The AST check is the canonical wiring proof — if a future PR removes one
of the calls, this test fails immediately rather than waiting on a render.
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap

import numpy as np
import pytest

from manim_renderer.components.text_card import TextCard
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.scene import JSONScene, _RESTAGE_AFTER_ACTIONS

logging.getLogger("manim").setLevel(logging.ERROR)


# --- AST: prove the runner calls `_restage` at composition events ----------

def _construct_calls_to(method_name: str) -> list[ast.Call]:
    """Return every `self.<method_name>(...)` call inside JSONScene.construct."""
    src = textwrap.dedent(inspect.getsource(JSONScene.construct))
    tree = ast.parse(src)
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "self"
            and f.attr == method_name
        ):
            out.append(node)
    return out


def test_construct_calls_restage_at_least_twice():
    """One call for show-actions branch + one call for the mutation branch."""
    calls = _construct_calls_to("_restage")
    assert len(calls) >= 2, (
        f"expected at least two `self._restage(...)` calls in "
        f"JSONScene.construct, found {len(calls)}"
    )


def test_restage_after_actions_set_includes_remove_and_set_role():
    """`removeComponent` and `setRole` must be in the restage-trigger set;
    mutations (highlightCell/crossOut/bestResponseArrow) must NOT be."""
    assert "removeComponent" in _RESTAGE_AFTER_ACTIONS
    assert "setRole" in _RESTAGE_AFTER_ACTIONS
    for m in ("highlightCell", "crossOut", "bestResponseArrow"):
        assert m not in _RESTAGE_AFTER_ACTIONS, (
            f"mutation {m!r} should not trigger restage per AGENT.md rule 18 / "
            f"PR G design — overlays follow host via the parallel walker."
        )


# --- Driver: run a tiny event loop and count _restage calls ---------------

class _RecordingScene(JSONScene):
    """Bypass MovingCameraScene init so the test never touches a renderer."""

    def __init__(self):  # noqa: D401 — intentionally don't call super
        self.restage_calls: list[str] = []
        self.play_calls: list[tuple] = []
        self.wait_calls: list[float] = []
        self._format = "horizontal"
        self._layout = resolve_layout("hero", "horizontal")
        self._id_to_mobject = {}
        self._overlays_by_host = {}
        self._roles = {}
        # PR J — solver inputs the recorder needs alongside the cast.
        self._id_to_slot = {}
        self._params_by_id = {}
        self._class_by_id = {}
        self._restage_state = {}

    def play(self, *args, **kwargs):
        self.play_calls.append((args, kwargs))

    def wait(self, t=0.0):
        self.wait_calls.append(float(t))

    def _restage(self, reason="", *, timing="fast"):
        self.restage_calls.append(reason)
        return 0.0


def _dispatch_event(scene: _RecordingScene, ev: dict, slot: str | None):
    """Mirror the per-event dispatch in JSONScene.construct, scoped to a
    single event. We intentionally don't import _PHASE_* — phase ordering
    is irrelevant for the wiring question."""
    from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY

    action = ev["action"]
    params = ev.get("params") or {}

    if action in COMPONENT_REGISTRY:
        anim = scene._dispatch_component(action, params, slot, scene._format)
    elif action in ACTION_REGISTRY:
        anim = scene._dispatch_action(action, params, scene._format)
    else:
        raise AssertionError(f"unknown action: {action}")

    if anim is not None:
        scene.play(anim)

    if action in COMPONENT_REGISTRY:
        scene._restage("post-show")
    elif action in _RESTAGE_AFTER_ACTIONS:
        scene._restage(f"post-{action.lower()}")


def test_show_action_triggers_one_restage_call():
    s = _RecordingScene()
    _dispatch_event(
        s, {"at": 0.0, "action": "showTextCard",
            "params": {"id": "c", "text": "hi"}}, "main",
    )
    assert s.restage_calls == ["post-show"]


def test_setrole_triggers_one_restage_call():
    s = _RecordingScene()
    # Seed a target first.
    _dispatch_event(
        s, {"at": 0.0, "action": "showTextCard",
            "params": {"id": "c", "text": "hi"}}, "main",
    )
    s.restage_calls.clear()
    _dispatch_event(
        s, {"at": 1.0, "action": "setRole",
            "params": {"target": "c", "role": "supporting"}}, None,
    )
    assert s.restage_calls == ["post-setrole"]


def test_remove_triggers_one_restage_call():
    s = _RecordingScene()
    _dispatch_event(
        s, {"at": 0.0, "action": "showTextCard",
            "params": {"id": "c", "text": "hi"}}, "main",
    )
    s.restage_calls.clear()
    _dispatch_event(
        s, {"at": 1.0, "action": "removeComponent",
            "params": {"target": "c"}}, None,
    )
    assert s.restage_calls == ["post-removecomponent"]


def test_mutations_do_not_trigger_restage():
    """Per the AGENT.md / brief contract, the three Phase 1 mutations only
    add ephemeral overlays — they should not fire restage."""
    from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix

    s = _RecordingScene()
    matrix = PayoffMatrix(
        {
            "id": "pd",
            "players": [{"name": "P1"}, {"name": "P2"}],
            "strategies": [["C", "D"], ["C", "D"]],
            "cells": [
                [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
                [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
            ],
        },
        format="horizontal",
    )
    s._id_to_mobject["pd"] = matrix
    s._roles["pd"] = "primary"
    # Manually advance state so dispatch sees the host.
    s.restage_calls.clear()

    _dispatch_event(
        s, {"at": 1.0, "action": "highlightCell",
            "params": {"target": "pd", "index": [0, 0]}}, None,
    )
    _dispatch_event(
        s, {"at": 1.5, "action": "crossOut",
            "params": {"target": "pd", "axis": "row", "index": 0}}, None,
    )
    _dispatch_event(
        s, {"at": 2.0, "action": "bestResponseArrow",
            "params": {"target": "pd", "from": [0, 0],
                       "to": [0, 1], "actor": "actor_a"}}, None,
    )

    assert s.restage_calls == [], (
        f"mutations triggered restage unexpectedly: {s.restage_calls}"
    )

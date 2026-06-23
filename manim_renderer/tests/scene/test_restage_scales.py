"""PR W — `_restage` actually scales mobjects.

The previous restage pass only animated `move_to(...)`. Even when the
solver returned a smaller target rect (e.g. after `setRole(target, "supporting")`),
the mobject kept its build-time size. These tests pin that scaling now
fires when target dims differ from the base size.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.text_card import TextCard
from manim_renderer.layouts.base import Rect
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.scene import JSONScene

logging.getLogger("manim").setLevel(logging.ERROR)


def _bare_scene(fmt: str = "horizontal", layout: str = "hero") -> JSONScene:
    scene = JSONScene.__new__(JSONScene)
    scene._layout = resolve_layout(layout, fmt)
    scene._format = fmt
    scene._id_to_mobject = {}
    scene._overlays_by_host = {}
    scene._roles = {}
    scene._id_to_slot = {}
    scene._params_by_id = {}
    scene._class_by_id = {}
    scene._restage_state = {}
    scene._restage_base_size = {}
    scene._play_calls = []
    scene.play = lambda *a, **kw: scene._play_calls.append((a, kw))
    return scene


def _text(id_: str) -> TextCard:
    return TextCard({"id": id_, "text": "hi"}, format="horizontal")


def test_restage_target_smaller_than_base_emits_scale_animation():
    """A target rect 50% the base size should trigger a scale on the
    animator passed to self.play."""
    s = _bare_scene()
    mob = _text("a")
    mob.move_to(np.array([0.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": mob}
    s._restage_base_size["a"] = (
        float(mob.width), float(mob.height),
    )

    # Patch _compute_target_rects to return a half-size target.
    base_w, base_h = s._restage_base_size["a"]
    half = Rect(cx=0.0, cy=0.0, width=base_w * 0.5, height=base_h * 0.5)
    s._compute_target_rects = lambda: {"a": half}

    rt = s._restage("test-shrink")

    assert rt > 0.0
    assert len(s._play_calls) == 1


def test_restage_identity_target_emits_no_animation():
    """Target rect that matches the base size triggers no Transform."""
    s = _bare_scene()
    mob = _text("a")
    mob.move_to(np.array([0.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": mob}
    s._restage_base_size["a"] = (float(mob.width), float(mob.height))

    same = Rect(
        cx=0.0, cy=0.0, width=float(mob.width), height=float(mob.height),
    )
    s._compute_target_rects = lambda: {"a": same}

    rt = s._restage("test-identity")

    assert rt == 0.0
    assert s._play_calls == []


def test_restage_target_at_new_center_emits_move():
    """Target rect at a different center triggers an animation."""
    s = _bare_scene()
    mob = _text("a")
    mob.move_to(np.array([0.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": mob}
    s._restage_base_size["a"] = (float(mob.width), float(mob.height))

    elsewhere = Rect(
        cx=3.0, cy=0.0, width=float(mob.width), height=float(mob.height),
    )
    s._compute_target_rects = lambda: {"a": elsewhere}

    rt = s._restage("test-move")

    assert rt > 0.0
    assert len(s._play_calls) == 1


def test_position_only_sentinel_restores_shrunk_host_to_natural():
    """A lone primary that a now-removed subject callout had shrunk must grow
    back to its natural (build-time) size when the solver returns a
    position-only sentinel — not stay stuck small."""
    s = _bare_scene()
    mob = _text("a")
    mob.move_to(np.array([0.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": mob}
    base_w, base_h = float(mob.width), float(mob.height)
    s._restage_base_size["a"] = (base_w, base_h)
    mob.scale(0.6)  # as a side callout's pack would have shrunk it

    # Solver returns a position-only sentinel (zero dims) for the lone primary.
    s._compute_target_rects = lambda: {
        "a": Rect(cx=0.0, cy=0.0, width=0.0, height=0.0)
    }

    rt = s._restage("test-restore")

    assert rt > 0.0  # a restore animation was queued (old code queued nothing)
    assert len(s._play_calls) == 1


def test_position_only_sentinel_leaves_natural_host_untouched():
    """A lone primary already at natural size gets no spurious scale from the
    position-only sentinel (no distortion / no needless motion)."""
    s = _bare_scene()
    mob = _text("a")
    mob.move_to(np.array([0.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": mob}
    s._restage_base_size["a"] = (float(mob.width), float(mob.height))

    s._compute_target_rects = lambda: {
        "a": Rect(cx=0.0, cy=0.0, width=0.0, height=0.0)
    }

    rt = s._restage("test-natural")

    assert rt == 0.0
    assert s._play_calls == []

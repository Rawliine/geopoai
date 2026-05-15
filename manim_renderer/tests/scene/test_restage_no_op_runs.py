"""PR G — `JSONScene._restage` exercises cleanly on identity inputs.

PR G ships restage as a no-op: the planner returns each cast member's
current bbox, so deltas are zero and `self.play` is never called. These
tests instantiate JSONScene via `__new__` (bypassing `construct()`'s
event loop), wire just enough state to make `_restage` callable, and
assert that the pass:

  * runs without raising,
  * captures a state snapshot for every live id,
  * returns 0.0 run-time (no movement),
  * leaves `_id_to_mobject` untouched,
  * never calls `self.play`.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.text_card import TextCard
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.scene import JSONScene

logging.getLogger("manim").setLevel(logging.ERROR)


def _bare_scene(fmt: str = "horizontal", layout: str = "hero") -> JSONScene:
    """Construct a JSONScene without firing Scene.__init__ — enough state
    so `_restage` and `_compute_target_rects` can run."""
    scene = JSONScene.__new__(JSONScene)
    scene._layout = resolve_layout(layout, fmt)
    scene._format = fmt
    scene._id_to_mobject = {}
    scene._overlays_by_host = {}
    scene._roles = {}
    # PR J — solver inputs the test fixture must seed alongside the cast.
    scene._id_to_slot = {}
    scene._params_by_id = {}
    scene._class_by_id = {}
    scene._restage_state = {}
    # Stub play so the test never depends on a Manim renderer.
    scene._play_calls = []
    scene.play = lambda *a, **kw: scene._play_calls.append((a, kw))
    return scene


def _text(id_: str, role: str = "primary") -> TextCard:
    return TextCard(
        {"id": id_, "text": "hi", "role": role},
        format="horizontal",
    )


def test_empty_cast_returns_zero():
    s = _bare_scene()
    assert s._restage("noop") == 0.0
    assert s._play_calls == []


def test_identity_returns_zero_and_does_not_play():
    s = _bare_scene()
    a = _text("a")
    b = _text("b")
    a.move_to(np.array([-2.0, 0.0, 0.0]))
    b.move_to(np.array([2.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": a, "b": b}
    s._roles = {"a": "primary", "b": "primary"}

    rt = s._restage("post-show")

    # PR G: identity planner → no animation.
    assert rt == 0.0
    assert s._play_calls == []
    # Cast roster untouched.
    assert set(s._id_to_mobject) == {"a", "b"}


def test_captures_restage_state_for_every_id():
    s = _bare_scene()
    a = _text("a")
    a.move_to(np.array([1.0, -0.5, 0.0]))
    s._id_to_mobject = {"a": a}

    s._restage("post-show")

    assert "a" in s._restage_state
    captured_center, captured_scale = s._restage_state["a"]
    np.testing.assert_allclose(captured_center, [1.0, -0.5, 0.0])
    assert captured_scale == 1.0


def test_compute_target_rects_returns_one_rect_per_id():
    s = _bare_scene()
    a = _text("a")
    b = _text("b")
    a.move_to(np.array([-1.0, 0.0, 0.0]))
    b.move_to(np.array([1.0, 0.0, 0.0]))
    s._id_to_mobject = {"a": a, "b": b}

    rects = s._compute_target_rects()

    assert set(rects) == {"a", "b"}
    # Centers match current bbox centers.
    np.testing.assert_allclose(rects["a"].center[:2], [-1.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(rects["b"].center[:2], [1.0, 0.0], atol=1e-6)
    # Width/height are positive (epsilon floor in PR G).
    assert rects["a"].width > 0 and rects["a"].height > 0


def test_restage_overlay_hook_is_silent_on_identity():
    """Overlays parented to a host should follow that host on Transform.
    On identity, the host doesn't move, so the overlay shouldn't either."""
    s = _bare_scene()
    a = _text("a")
    s._id_to_mobject = {"a": a}
    # Fake overlay — any mobject with width/height suffices for the dict.
    overlay = _text("ov")
    s._overlays_by_host = {"a": [overlay]}

    rt = s._restage("post-show")

    assert rt == 0.0
    assert s._play_calls == []


@pytest.mark.parametrize("reason", [
    "post-show", "post-removecomponent", "post-setrole", "any-string", "",
])
def test_reason_string_is_accepted_unchanged(reason):
    """The `reason` parameter is purely diagnostic — every string value is
    accepted without affecting behavior."""
    s = _bare_scene()
    s._id_to_mobject = {"a": _text("a")}
    assert s._restage(reason) == 0.0

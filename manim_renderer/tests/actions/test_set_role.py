"""Unit tests for `actions.set_role` (PR F).

The callable is a no-op for animation purposes — it records the new role in
`scene._roles[target]` and updates the component's `role` attr, then returns
None. PR G consumes the new role via a restage pass; this PR just proves the
recording happens.
"""

from __future__ import annotations

import logging

import pytest

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.set_role import set_role
from manim_renderer.components.text_card import TextCard

logging.getLogger("manim").setLevel(logging.ERROR)


class _StubScene:
    """Stand-in for JSONScene; just holds _roles."""

    def __init__(self):
        self._roles: dict[str, str] = {}


def _card(role: str | None = None) -> TextCard:
    params: dict = {"id": "card", "text": "hi"}
    if role is not None:
        params["role"] = role
    return TextCard(params, format="horizontal")


def _ctx(params: dict, mob: TextCard, scene: _StubScene | None = None) -> ActionContext:
    return ActionContext(
        params=params,
        id_to_mobject={"card": mob},
        format="horizontal",
        scene=scene,
    )


# --- happy path -----------------------------------------------------------


def test_returns_none_pr_f_is_no_animation():
    card = _card()
    scene = _StubScene()
    result = set_role(_ctx({"target": "card", "role": "supporting"}, card, scene))
    assert result is None


def test_records_role_on_scene():
    card = _card()
    scene = _StubScene()
    set_role(_ctx({"target": "card", "role": "supporting"}, card, scene))
    assert scene._roles == {"card": "supporting"}


def test_updates_component_role_attr():
    card = _card()  # defaults to "primary"
    assert card.role == "primary"
    scene = _StubScene()
    set_role(_ctx({"target": "card", "role": "ambient"}, card, scene))
    assert card.role == "ambient"


@pytest.mark.parametrize("role", [
    "hero", "primary", "supporting", "ambient", "annotation", "hidden",
])
def test_accepts_all_six_roles(role):
    card = _card()
    scene = _StubScene()
    set_role(_ctx({"target": "card", "role": role}, card, scene))
    assert scene._roles["card"] == role


def test_repeated_set_role_overwrites():
    card = _card()
    scene = _StubScene()
    set_role(_ctx({"target": "card", "role": "supporting"}, card, scene))
    set_role(_ctx({"target": "card", "role": "ambient"}, card, scene))
    assert scene._roles["card"] == "ambient"
    assert card.role == "ambient"


# --- error paths ----------------------------------------------------------


def test_missing_target_raises():
    card = _card()
    scene = _StubScene()
    with pytest.raises(ValueError, match="target"):
        set_role(_ctx({"role": "supporting"}, card, scene))


def test_missing_role_raises():
    card = _card()
    scene = _StubScene()
    with pytest.raises(ValueError, match="role"):
        set_role(_ctx({"target": "card"}, card, scene))


def test_unknown_target_raises():
    card = _card()
    scene = _StubScene()
    with pytest.raises(ValueError, match="not in id registry"):
        set_role(_ctx({"target": "ghost", "role": "supporting"}, card, scene))


# --- scene-less invocation -----------------------------------------------


def test_no_scene_does_not_crash():
    """Action callables run with scene=None in some unit tests; recording
    should be skipped rather than raising."""
    card = _card()
    ctx = ActionContext(
        params={"target": "card", "role": "supporting"},
        id_to_mobject={"card": card},
        format="horizontal",
        scene=None,
    )
    set_role(ctx)  # must not raise
    # Component's own attr still updates so future preferred_size() reads
    # the new value.
    assert card.role == "supporting"


def test_default_role_is_primary_for_text_card():
    card = _card()
    assert card.role == "primary"


def test_explicit_role_param_on_construction():
    card = _card(role="supporting")
    assert card.role == "supporting"

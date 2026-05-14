"""Tests for the three PayoffMatrix mutation actions.

These exercise the action callable directly with a hand-built ActionContext,
not the scene runner. The scene runner just dispatches into the action; the
contract we care about here is: action validates params, looks up target,
and returns a sensible Animation.
"""

from __future__ import annotations

import logging

import pytest

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.best_response_arrow import best_response_arrow
from manim_renderer.actions.cross_out import cross_out
from manim_renderer.actions.highlight_cell import highlight_cell
from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix

logging.getLogger("manim").setLevel(logging.ERROR)


def _matrix() -> PayoffMatrix:
    return PayoffMatrix(
        {
            "id": "m",
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


def _ctx(params: dict, matrix: PayoffMatrix) -> ActionContext:
    return ActionContext(
        params=params,
        id_to_mobject={"m": matrix},
        format="horizontal",
        scene=None,  # not used by Phase 1 mutations
    )


# --- highlightCell ---------------------------------------------------------

def test_highlight_cell_returns_fade_in():
    from manim import FadeIn
    m = _matrix()
    anim = highlight_cell(_ctx(
        {"target": "m", "index": [1, 1], "color": "highlight"}, m
    ))
    assert isinstance(anim, FadeIn)


def test_highlight_cell_requires_target():
    m = _matrix()
    with pytest.raises(ValueError, match="target"):
        highlight_cell(_ctx({"index": [0, 0]}, m))


def test_highlight_cell_unknown_target():
    m = _matrix()
    with pytest.raises(ValueError, match="not in id registry"):
        highlight_cell(_ctx({"target": "nope", "index": [0, 0]}, m))


def test_highlight_cell_requires_index_pair():
    m = _matrix()
    with pytest.raises(ValueError, match="index"):
        highlight_cell(_ctx({"target": "m"}, m))


def test_highlight_cell_unknown_color():
    m = _matrix()
    with pytest.raises(ValueError, match="palette"):
        highlight_cell(_ctx(
            {"target": "m", "index": [0, 0], "color": "puce"}, m
        ))


def test_highlight_cell_wrong_target_type():
    """A target that isn't a PayoffMatrix must fail loudly."""
    class _Other:
        id = "other"

    other = _Other()
    ctx = ActionContext(
        params={"target": "other", "index": [0, 0]},
        id_to_mobject={"other": other},
        format="horizontal",
        scene=None,
    )
    with pytest.raises(ValueError, match="PayoffMatrix-shaped"):
        highlight_cell(ctx)


# --- crossOut -------------------------------------------------------------

def test_cross_out_row_returns_create():
    from manim import Create
    m = _matrix()
    anim = cross_out(_ctx(
        {"target": "m", "axis": "row", "index": 0}, m
    ))
    assert isinstance(anim, Create)


def test_cross_out_col_returns_create():
    from manim import Create
    m = _matrix()
    anim = cross_out(_ctx(
        {"target": "m", "axis": "col", "index": 1}, m
    ))
    assert isinstance(anim, Create)


def test_cross_out_dashed_style():
    from manim import Create, DashedLine
    m = _matrix()
    anim = cross_out(_ctx(
        {"target": "m", "axis": "row", "index": 0, "style": "dashed"}, m
    ))
    assert isinstance(anim, Create)
    # The Create wraps the line; underlying mobject is DashedLine.
    assert isinstance(anim.mobject, DashedLine)


def test_cross_out_bad_axis():
    m = _matrix()
    with pytest.raises(ValueError, match="axis"):
        cross_out(_ctx({"target": "m", "axis": "diag", "index": 0}, m))


def test_cross_out_bad_style():
    m = _matrix()
    with pytest.raises(ValueError, match="style"):
        cross_out(_ctx(
            {"target": "m", "axis": "row", "index": 0, "style": "squiggle"}, m
        ))


# --- bestResponseArrow ----------------------------------------------------

def test_best_response_arrow_returns_create():
    from manim import Arrow, Create
    m = _matrix()
    anim = best_response_arrow(_ctx(
        {"target": "m", "from": [0, 0], "to": [0, 1], "actor": "actor_a"}, m
    ))
    assert isinstance(anim, Create)
    assert isinstance(anim.mobject, Arrow)


def test_best_response_arrow_unknown_actor():
    m = _matrix()
    with pytest.raises(ValueError, match="actor"):
        best_response_arrow(_ctx(
            {"target": "m", "from": [0, 0], "to": [0, 1], "actor": "lavender"}, m
        ))


def test_best_response_arrow_bad_from():
    m = _matrix()
    with pytest.raises(ValueError, match="from"):
        best_response_arrow(_ctx(
            {"target": "m", "from": "a", "to": [0, 1], "actor": "actor_a"}, m
        ))


# --- Phase 1.5 overlay tracking -------------------------------------------


class _StubScene:
    """Stand-in for JSONScene in unit tests; just holds _overlays_by_host."""

    def __init__(self):
        self._overlays_by_host: dict[str, list] = {}


def _ctx_with_scene(params: dict, matrix: PayoffMatrix, scene: _StubScene) -> ActionContext:
    return ActionContext(
        params=params,
        id_to_mobject={"m": matrix},
        format="horizontal",
        scene=scene,
    )


def test_highlight_cell_registers_overlay_against_host():
    m = _matrix()
    scene = _StubScene()
    highlight_cell(_ctx_with_scene(
        {"target": "m", "index": [0, 0], "color": "highlight"}, m, scene
    ))
    assert "m" in scene._overlays_by_host
    assert len(scene._overlays_by_host["m"]) == 1


def test_cross_out_registers_overlay_against_host():
    m = _matrix()
    scene = _StubScene()
    cross_out(_ctx_with_scene(
        {"target": "m", "axis": "row", "index": 0}, m, scene
    ))
    assert len(scene._overlays_by_host["m"]) == 1


def test_best_response_arrow_registers_overlay_against_host():
    m = _matrix()
    scene = _StubScene()
    best_response_arrow(_ctx_with_scene(
        {"target": "m", "from": [0, 0], "to": [0, 1], "actor": "actor_a"}, m, scene,
    ))
    assert len(scene._overlays_by_host["m"]) == 1


def test_multiple_overlays_accumulate_against_same_host():
    m = _matrix()
    scene = _StubScene()
    highlight_cell(_ctx_with_scene({"target": "m", "index": [0, 0]}, m, scene))
    highlight_cell(_ctx_with_scene({"target": "m", "index": [1, 1]}, m, scene))
    cross_out(_ctx_with_scene({"target": "m", "axis": "row", "index": 0}, m, scene))
    assert len(scene._overlays_by_host["m"]) == 3


def test_overlay_opt_in_id_is_registered_in_id_to_mobject():
    """3b — when `id` is provided, the overlay is addressable like a component."""
    m = _matrix()
    scene = _StubScene()
    ctx = ActionContext(
        params={"target": "m", "index": [0, 0], "id": "my-highlight"},
        id_to_mobject={"m": m},
        format="horizontal",
        scene=scene,
    )
    highlight_cell(ctx)
    assert "my-highlight" in ctx.id_to_mobject
    assert ctx.id_to_mobject["my-highlight"] is scene._overlays_by_host["m"][0]


def test_overlay_id_collision_raises():
    m = _matrix()
    scene = _StubScene()
    ctx = ActionContext(
        params={"target": "m", "index": [0, 0], "id": "m"},  # collides with host
        id_to_mobject={"m": m},
        format="horizontal",
        scene=scene,
    )
    with pytest.raises(ValueError, match="collides"):
        highlight_cell(ctx)


def test_remove_component_chains_overlay_fades():
    """3a — removeComponent should fade host + all registered overlays."""
    from manim import AnimationGroup
    from manim_renderer.actions.remove_component import remove_component

    m = _matrix()
    scene = _StubScene()
    # Register 2 overlays against m
    highlight_cell(_ctx_with_scene({"target": "m", "index": [0, 0]}, m, scene))
    cross_out(_ctx_with_scene({"target": "m", "axis": "row", "index": 0}, m, scene))

    ctx = ActionContext(
        params={"target": "m"},
        id_to_mobject={"m": m},
        format="horizontal",
        scene=scene,
    )
    anim = remove_component(ctx)
    # Should produce an AnimationGroup wrapping host + 2 overlays.
    assert isinstance(anim, AnimationGroup)
    # Overlay registry should be cleared for this host.
    assert "m" not in scene._overlays_by_host
    # Host id dropped.
    assert "m" not in ctx.id_to_mobject


def test_remove_component_drops_overlay_id_from_registry():
    """3a + 3b — if an overlay had an opt-in id, removeComponent of host
    should drop the overlay id too (so future references fail loudly)."""
    from manim_renderer.actions.remove_component import remove_component

    m = _matrix()
    scene = _StubScene()
    ctx_hl = ActionContext(
        params={"target": "m", "index": [0, 0], "id": "h1"},
        id_to_mobject={"m": m},
        format="horizontal",
        scene=scene,
    )
    highlight_cell(ctx_hl)
    assert "h1" in ctx_hl.id_to_mobject

    ctx_rm = ActionContext(
        params={"target": "m"},
        id_to_mobject=ctx_hl.id_to_mobject,
        format="horizontal",
        scene=scene,
    )
    remove_component(ctx_rm)
    assert "h1" not in ctx_rm.id_to_mobject
    assert "m" not in ctx_rm.id_to_mobject


def test_remove_component_no_overlays_returns_simple_anim():
    """When no overlays registered, remove_component returns the host exit
    directly (not wrapped in AnimationGroup)."""
    from manim import FadeOut
    from manim_renderer.actions.remove_component import remove_component

    m = _matrix()
    scene = _StubScene()
    ctx = ActionContext(
        params={"target": "m"},
        id_to_mobject={"m": m},
        format="horizontal",
        scene=scene,
    )
    anim = remove_component(ctx)
    assert isinstance(anim, FadeOut)

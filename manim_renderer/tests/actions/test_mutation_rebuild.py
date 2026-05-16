"""Mutation overlays expose a `_rebuild_recipe` so the runner can
reconstruct them against a host at its target state during restage.
This keeps geometry-bound overlays (matrix cell highlights, arrow
endpoints between cells, dashed strike-out lines) aligned when the
host scales and moves.
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


class _FakeScene:
    def __init__(self):
        self._overlays_by_host: dict = {}


def _ctx(matrix: PayoffMatrix, params: dict) -> ActionContext:
    return ActionContext(
        params=params,
        id_to_mobject={"pd": matrix},
        format="horizontal",
        scene=_FakeScene(),
    )


@pytest.mark.parametrize("action_fn,extra_params", [
    (highlight_cell, {"index": [0, 0], "color": "highlight"}),
    (cross_out,      {"axis": "row", "index": 0, "style": "strike"}),
    (best_response_arrow, {"from": [0, 0], "to": [1, 1],
                            "actor": "actor_a"}),
])
def test_mutation_overlay_exposes_rebuild_recipe(action_fn, extra_params):
    """Every mutation overlay attaches a rebuild recipe on its mobject
    so the restage walker can reconstruct it against a new host."""
    matrix = _matrix()
    ctx = _ctx(matrix, {"target": "pd", **extra_params})
    action_fn(ctx)
    overlays = ctx.scene._overlays_by_host["pd"]
    assert len(overlays) == 1
    overlay = overlays[0]
    recipe = getattr(overlay, "_rebuild_recipe", None)
    assert callable(recipe), (
        f"{action_fn.__name__} did not attach a _rebuild_recipe"
    )


def test_highlight_cell_recipe_against_translated_host_moves_overlay():
    """The recipe queries the host's anchors live, so passing a
    translated host copy yields an overlay at the new cell center."""
    import numpy as np

    matrix = _matrix()
    ctx = _ctx(matrix, {"target": "pd", "index": [1, 0],
                          "color": "highlight"})
    highlight_cell(ctx)
    overlay = ctx.scene._overlays_by_host["pd"][0]
    recipe = overlay._rebuild_recipe

    original_center = overlay.get_center()
    translated_host = matrix.copy().shift(np.array([3.0, -1.0, 0.0]))
    rebuilt = recipe(translated_host)
    rebuilt_center = rebuilt.get_center()

    # The rebuilt overlay must follow the host's translation.
    np.testing.assert_allclose(
        rebuilt_center - original_center,
        np.array([3.0, -1.0, 0.0]),
        atol=1e-4,
    )


def test_best_response_arrow_recipe_yields_arrow_at_new_endpoints():
    """Arrow endpoints come from the host's cell anchors. After a
    translated host copy, the rebuilt arrow's endpoints match."""
    import numpy as np

    matrix = _matrix()
    ctx = _ctx(matrix, {"target": "pd", "from": [0, 0], "to": [1, 1],
                          "actor": "actor_a"})
    best_response_arrow(ctx)
    overlay = ctx.scene._overlays_by_host["pd"][0]
    recipe = overlay._rebuild_recipe

    shifted_host = matrix.copy().shift(np.array([2.5, 0.0, 0.0]))
    rebuilt = recipe(shifted_host)

    # Endpoints align with the shifted matrix's cell anchors (modulo
    # the Arrow's own buff trim — assert proximity, not exact).
    new_start = np.asarray(shifted_host.get_anchor("cell:0,0"))
    new_end = np.asarray(shifted_host.get_anchor("cell:1,1"))
    arrow_dir = new_end - new_start
    rebuilt_dir = rebuilt.get_end() - rebuilt.get_start()
    cosine = np.dot(arrow_dir, rebuilt_dir) / (
        np.linalg.norm(arrow_dir) * np.linalg.norm(rebuilt_dir)
    )
    # Both arrows point in the same direction (cosine ≈ 1.0).
    assert cosine > 0.99

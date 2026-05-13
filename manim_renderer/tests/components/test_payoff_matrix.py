"""PayoffMatrix unit tests. Construction + anchors + entrance."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix

logging.getLogger("manim").setLevel(logging.ERROR)


def _pd_params():
    return {
        "id": "m",
        "players": [{"name": "P1"}, {"name": "P2"}],
        "strategies": [["C", "D"], ["C", "D"]],
        "cells": [
            [{"a": 3, "b": 3}, {"a": 0, "b": 5}],
            [{"a": 5, "b": 0}, {"a": 1, "b": 1}],
        ],
    }


def _three_by_three():
    p = _pd_params()
    p["strategies"] = [["X", "Y", "Z"], ["P", "Q", "R"]]
    p["cells"] = [[{"a": i + j, "b": i * j} for j in range(3)] for i in range(3)]
    return p


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    assert m.id == "m"
    assert m.n_rows() == 2 and m.n_cols() == 2


def test_three_by_three_construction():
    m = PayoffMatrix(_three_by_three(), format="horizontal")
    assert m.n_rows() == 3 and m.n_cols() == 3


def test_too_few_players_rejected():
    p = _pd_params()
    p["players"] = [{"name": "P1"}]
    with pytest.raises(ValueError, match="2 players"):
        PayoffMatrix(p, format="horizontal")


def test_cells_shape_mismatch():
    p = _pd_params()
    p["cells"] = [[{"a": 1, "b": 2}]]  # 1x1 but strategies say 2x2
    with pytest.raises(ValueError, match="shape mismatch"):
        PayoffMatrix(p, format="horizontal")


def test_unknown_player_color_raises():
    p = _pd_params()
    p["players"][0]["color"] = "puce"
    with pytest.raises(ValueError, match="palette key"):
        PayoffMatrix(p, format="horizontal")


# --- both formats -----------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    m = PayoffMatrix(_pd_params(), format=fmt)
    assert m.width > 0 and m.height > 0


# --- anchors ---------------------------------------------------------------

def test_cell_anchor():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    coord = m.get_anchor("cell:1,1")
    np.testing.assert_array_almost_equal(coord, m._cell_rects[(1, 1)].get_center())


def test_cell_anchor_out_of_bounds():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    with pytest.raises(KeyError, match="out of bounds"):
        m.get_anchor("cell:5,5")


def test_cell_anchor_bad_format():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    with pytest.raises(KeyError, match="i,j"):
        m.get_anchor("cell:notanint")


def test_row_anchor():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    coord = m.get_anchor("row:1")
    np.testing.assert_array_almost_equal(coord, m._row_labels[1].get_center())


def test_col_anchor():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    coord = m.get_anchor("col:0")
    np.testing.assert_array_almost_equal(coord, m._col_labels[0].get_center())


def test_row_out_of_range():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    with pytest.raises(KeyError, match="out of range"):
        m.get_anchor("row:9")


# --- helpers for mutation actions ------------------------------------------

def test_cell_dims_positive():
    m = PayoffMatrix(_pd_params(), format="horizontal")
    w, h = m.cell_dims()
    assert w > 0 and h > 0


def test_player_color_accessors():
    p = _pd_params()
    p["players"][0]["color"] = "actor_a"
    p["players"][1]["color"] = "actor_b"
    m = PayoffMatrix(p, format="horizontal")
    assert m.row_player_color().startswith("#")
    assert m.col_player_color().startswith("#")
    assert m.row_player_color() != m.col_player_color()


# --- entrance --------------------------------------------------------------

def test_level_by_level_entrance():
    from manim import Succession
    m = PayoffMatrix(_pd_params(), format="horizontal")
    anim = m.entrance("level-by-level", "normal")
    assert isinstance(anim, Succession)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    m = PayoffMatrix(_pd_params(), format="horizontal")
    anim = m.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

"""GameTree unit tests. Construction + layout + anchors + format behavior."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.game_theory.game_tree import GameTree

logging.getLogger("manim").setLevel(logging.ERROR)


def _simple_tree():
    return {
        "label": "P1",
        "children": [
            {"label": "C", "edge": "C", "children": [
                {"label": "(3,3)", "edge": "C"},
                {"label": "(0,5)", "edge": "D"},
            ]},
            {"label": "D", "edge": "D", "children": [
                {"label": "(5,0)", "edge": "C"},
                {"label": "(1,1)", "edge": "D"},
            ]},
        ],
    }


def _deep_tree(depth=6):
    """Linear deep tree for max_depth testing."""
    node = {"label": f"L{depth}"}
    for d in range(depth - 1, 0, -1):
        node = {"label": f"L{d}", "children": [node]}
    return node


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    assert t.id == "t"
    # 1 root + 2 mid + 4 leaves = 7 nodes
    assert len(t._path_to_mob) == 7


def test_requires_nodes():
    with pytest.raises(ValueError, match="nodes"):
        GameTree({"id": "t"}, format="horizontal")


def test_node_requires_label():
    with pytest.raises(ValueError, match="label"):
        GameTree(
            {"id": "t", "nodes": {"children": [{"label": "x"}]}},
            format="horizontal",
        )


def test_unknown_color_raises():
    with pytest.raises(ValueError, match="palette key"):
        GameTree(
            {"id": "t", "nodes": {"label": "P1", "color": "puce"}},
            format="horizontal",
        )


# --- both formats -----------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format=fmt)
    assert t.width > 0 and t.height > 0


# --- layout ----------------------------------------------------------------

def test_horizontal_root_on_left():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    # Root is left of leaves on the x-axis.
    root_x = t._path_to_mob["root"].get_center()[0]
    leaf_x = t._path_to_mob["root.0.0"].get_center()[0]
    assert leaf_x > root_x


def test_vertical_root_on_top():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="vertical")
    root_y = t._path_to_mob["root"].get_center()[1]
    leaf_y = t._path_to_mob["root.0.0"].get_center()[1]
    assert leaf_y < root_y


# --- depth cap (vertical only) ----------------------------------------------

def test_vertical_depth_cap():
    t = GameTree(
        {"id": "t", "nodes": _deep_tree(8), "max_depth": 3},
        format="vertical",
    )
    # Only 3 levels (root, root.0, root.0.0) — deeper nodes dropped.
    assert "root.0.0" in t._path_to_mob
    assert "root.0.0.0" not in t._path_to_mob


def test_horizontal_does_not_apply_depth_cap():
    t = GameTree(
        {"id": "t", "nodes": _deep_tree(6), "max_depth": 3},
        format="horizontal",
    )
    # Horizontal renders the full tree regardless of max_depth.
    assert "root.0.0.0.0" in t._path_to_mob


# --- anchors ---------------------------------------------------------------

def test_node_root_anchor():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    coord = t.get_anchor("node:root")
    np.testing.assert_array_almost_equal(
        coord, t._path_to_mob["root"].get_center()
    )


def test_node_child_anchor():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    coord = t.get_anchor("node:root.0")
    np.testing.assert_array_almost_equal(
        coord, t._path_to_mob["root.0"].get_center()
    )


def test_node_unknown_path_raises():
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    with pytest.raises(KeyError, match="no node at path"):
        t.get_anchor("node:nonexistent")


# --- entrance --------------------------------------------------------------

def test_level_by_level_entrance():
    from manim import AnimationGroup
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    anim = t.entrance("level-by-level", "normal")
    assert isinstance(anim, AnimationGroup)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    t = GameTree({"id": "t", "nodes": _simple_tree()}, format="horizontal")
    anim = t.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

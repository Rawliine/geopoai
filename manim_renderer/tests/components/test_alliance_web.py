"""AllianceWeb unit tests. Construction + layout determinism + anchors."""

from __future__ import annotations

import logging
import math

import numpy as np
import pytest

from manim_renderer.components.geopolitical.alliance_web import AllianceWeb

logging.getLogger("manim").setLevel(logging.ERROR)


def _three_nodes():
    return [
        {"id": "usa", "label": "USA", "color": "actor_a"},
        {"id": "rus", "label": "Russia", "color": "actor_b"},
        {"id": "chn", "label": "China", "color": "actor_c"},
    ]


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    w = AllianceWeb(
        {"id": "w", "nodes": _three_nodes(),
         "edges": [{"from": "usa", "to": "rus", "kind": "rivalry"}]},
        format="horizontal",
    )
    assert w.id == "w"
    assert len(w._node_mobs) == 3
    assert len(w._edge_mobs) == 1


def test_requires_nodes():
    with pytest.raises(ValueError, match="nodes"):
        AllianceWeb({"id": "w"}, format="horizontal")


def test_duplicate_node_id_rejected():
    bad = [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]
    with pytest.raises(ValueError, match="duplicate"):
        AllianceWeb({"id": "w", "nodes": bad}, format="horizontal")


def test_edge_from_unknown_node():
    with pytest.raises(ValueError, match="edge.from"):
        AllianceWeb(
            {"id": "w", "nodes": _three_nodes(),
             "edges": [{"from": "mars", "to": "rus"}]},
            format="horizontal",
        )


def test_edge_to_unknown_node():
    with pytest.raises(ValueError, match="edge.to"):
        AllianceWeb(
            {"id": "w", "nodes": _three_nodes(),
             "edges": [{"from": "usa", "to": "venus"}]},
            format="horizontal",
        )


def test_edge_invalid_kind():
    with pytest.raises(ValueError, match="edge.kind"):
        AllianceWeb(
            {"id": "w", "nodes": _three_nodes(),
             "edges": [{"from": "usa", "to": "rus", "kind": "trade"}]},
            format="horizontal",
        )


def test_unknown_color_raises():
    bad = [{"id": "a", "color": "puce"}]
    with pytest.raises(ValueError, match="palette key"):
        AllianceWeb({"id": "w", "nodes": bad}, format="horizontal")


# --- both formats -----------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format=fmt)
    assert w.width > 0 and w.height > 0


# --- layout determinism ----------------------------------------------------

def test_seed_is_deterministic():
    nodes = _three_nodes()
    w1 = AllianceWeb({"id": "w", "nodes": nodes, "seed": 7}, format="horizontal")
    w2 = AllianceWeb({"id": "w", "nodes": nodes, "seed": 7}, format="horizontal")
    for nid in ("usa", "rus", "chn"):
        np.testing.assert_array_almost_equal(
            w1._positions[nid], w2._positions[nid]
        )


def test_different_seeds_yield_different_positions():
    nodes = _three_nodes()
    w1 = AllianceWeb({"id": "w", "nodes": nodes, "seed": 0}, format="horizontal")
    w2 = AllianceWeb({"id": "w", "nodes": nodes, "seed": 90}, format="horizontal")
    # At least one node should sit somewhere different.
    assert any(
        not np.allclose(w1._positions[nid], w2._positions[nid])
        for nid in ("usa", "rus", "chn")
    )


def test_nodes_on_circle():
    w = AllianceWeb(
        {"id": "w", "nodes": _three_nodes(), "seed": 0},
        format="horizontal",
    )
    # All node positions equidistant from origin.
    radii = [np.linalg.norm(w._positions[nid]) for nid in w._node_ids]
    for r in radii[1:]:
        assert math.isclose(r, radii[0], rel_tol=1e-6)


# --- anchors ---------------------------------------------------------------

def test_node_anchor_returns_circle_center():
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format="horizontal")
    coord = w.get_anchor("node:usa")
    np.testing.assert_array_almost_equal(coord, w._node_mobs["usa"].get_center())


def test_node_anchor_unknown_id():
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format="horizontal")
    with pytest.raises(KeyError, match="no node"):
        w.get_anchor("node:mars")


# --- child id registration --------------------------------------------------

def test_extra_id_registrations_exposes_all_node_ids():
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format="horizontal")
    extras = w.extra_id_registrations()
    assert set(extras) == {"usa", "rus", "chn"}


# --- entrance --------------------------------------------------------------

def test_level_by_level_with_edges():
    from manim import Succession
    w = AllianceWeb(
        {"id": "w", "nodes": _three_nodes(),
         "edges": [{"from": "usa", "to": "rus"}]},
        format="horizontal",
    )
    anim = w.entrance("level-by-level", "normal")
    assert isinstance(anim, Succession)


def test_level_by_level_no_edges():
    from manim import LaggedStart
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format="horizontal")
    anim = w.entrance("level-by-level", "normal")
    assert isinstance(anim, LaggedStart)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    w = AllianceWeb({"id": "w", "nodes": _three_nodes()}, format="horizontal")
    anim = w.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

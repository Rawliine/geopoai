"""Timeline unit tests. Construction + anchors + entrance + format behavior."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.narrative.timeline import Timeline

logging.getLogger("manim").setLevel(logging.ERROR)


def _events(n=4):
    return [
        {"id": f"e{i}", "at_label": f"{1900 + i*10}", "label": f"Event {i}"}
        for i in range(n)
    ]


# --- construction -----------------------------------------------------------

def test_minimal_construction():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    assert tl.id == "t"
    assert len(tl._dots) == 3
    assert len(tl._label_mobs) == 3
    assert hasattr(tl, "_axis")


def test_requires_events():
    with pytest.raises(ValueError, match="events"):
        Timeline({"id": "t"}, format="horizontal")


def test_rejects_empty_events():
    with pytest.raises(ValueError, match="events"):
        Timeline({"id": "t", "events": []}, format="horizontal")


def test_unknown_color_raises():
    bad = [{"label": "x", "color": "puce"}]
    with pytest.raises(ValueError, match="palette key"):
        Timeline({"id": "t", "events": bad}, format="horizontal")


# --- format-aware behavior --------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    tl = Timeline({"id": "t", "events": _events(4)}, format=fmt)
    assert tl.width > 0 and tl.height > 0


def test_horizontal_dots_collinear_on_axis():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    ys = [d.get_center()[1] for d in tl._dots]
    # All dots share a single y (collinear on the axis). The actual y is not
    # zero because the parent VGroup's bbox recenters when labels of different
    # heights sit above/below — we only care that the axis is a straight line.
    assert max(ys) - min(ys) < 1e-6, ys
    # X coords are monotonically increasing.
    xs = [d.get_center()[0] for d in tl._dots]
    assert xs == sorted(xs)


def test_vertical_dots_collinear_on_axis():
    tl = Timeline({"id": "t", "events": _events(3)}, format="vertical")
    xs = [d.get_center()[0] for d in tl._dots]
    # All dots share a single x (collinear on the vertical axis).
    assert max(xs) - min(xs) < 1e-6, xs
    # Y coords are monotonically decreasing (top -> bottom).
    ys = [d.get_center()[1] for d in tl._dots]
    assert ys == sorted(ys, reverse=True)


def test_vertical_caps_at_max_visible():
    events = _events(15)
    tl = Timeline({"id": "t", "events": events, "max_visible": 5}, format="vertical")
    assert len(tl._dots) == 5


def test_horizontal_does_not_cap():
    events = _events(15)
    tl = Timeline({"id": "t", "events": events, "max_visible": 5}, format="horizontal")
    assert len(tl._dots) == 15


# --- alternating labels (horizontal) ---------------------------------------

def test_horizontal_labels_alternate_above_below():
    tl = Timeline({"id": "t", "events": _events(4)}, format="horizontal")
    ys = [lbl.get_center()[1] for lbl in tl._label_mobs]
    # Even indices above (y > 0), odd indices below (y < 0).
    assert ys[0] > 0 and ys[1] < 0 and ys[2] > 0 and ys[3] < 0


# --- anchors ----------------------------------------------------------------

def test_event_anchor_by_index():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    coord = tl.get_anchor("event:1")
    np.testing.assert_array_almost_equal(coord, tl._dots[1].get_center())


def test_event_anchor_by_id():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    coord = tl.get_anchor("event:e2")
    np.testing.assert_array_almost_equal(coord, tl._dots[2].get_center())


def test_event_label_anchor():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    coord = tl.get_anchor("event:0.label")
    np.testing.assert_array_almost_equal(coord, tl._label_mobs[0].get_center())


def test_event_date_anchor_raises_if_no_at_label():
    events = [{"id": "x", "label": "no date"}]
    tl = Timeline({"id": "t", "events": events}, format="horizontal")
    with pytest.raises(KeyError, match="at_label"):
        tl.get_anchor("event:x.date")


def test_event_anchor_unknown_id():
    tl = Timeline({"id": "t", "events": _events(2)}, format="horizontal")
    with pytest.raises(KeyError, match="no event"):
        tl.get_anchor("event:nonexistent")


def test_event_suffix_invalid():
    tl = Timeline({"id": "t", "events": _events(2)}, format="horizontal")
    with pytest.raises(KeyError, match="label.*date"):
        tl.get_anchor("event:0.foo")


# --- child id registration --------------------------------------------------

def test_extra_id_registrations_exposes_named_events():
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    extras = tl.extra_id_registrations()
    assert set(extras) == {"e0", "e1", "e2"}
    for eid, dot in extras.items():
        assert dot in tl._dots


def test_unnamed_events_not_exposed():
    events = [
        {"id": "named", "label": "x"},
        {"label": "anon"},
    ]
    tl = Timeline({"id": "t", "events": events}, format="horizontal")
    assert set(tl.extra_id_registrations()) == {"named"}


# --- entrance ---------------------------------------------------------------

def test_level_by_level_entrance():
    from manim import Succession
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    anim = tl.entrance("level-by-level", "normal")
    assert isinstance(anim, Succession)


def test_fade_in_dispatches_to_base():
    from manim import FadeIn
    tl = Timeline({"id": "t", "events": _events(3)}, format="horizontal")
    anim = tl.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

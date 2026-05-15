"""PR L — `pick_subject_side` picks the best anchor token for a callout.

Contract:
  * Horizontal: prefer `right-of`; fall back to `left-of`, then `below`,
    then `above`.
  * Vertical: prefer `below`; fall back to `above`, then `right-of`,
    then `left-of`.
  * When the preferred side is blocked by the frame edge, switch.
  * `parse_subject` splits subject strings reliably.
"""

from __future__ import annotations

import pytest
from manim import Rectangle

from manim_renderer.resolvers.subject_placement import (
    parse_subject,
    pick_subject_side,
    resolve_subject_target,
)


def _rect(cx: float, cy: float, w: float = 2.0, h: float = 2.0):
    """Build a Manim Rectangle positioned at (cx, cy). Bbox accessors are
    real Manim mobject methods so the picker exercises the same path it
    uses in production."""
    r = Rectangle(width=w, height=h)
    r.move_to([cx, cy, 0])
    return r


# --- horizontal preferences ----------------------------------------------


def test_horizontal_prefers_right_of_when_subject_centered():
    subject = _rect(0.0, 0.0)
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side == "right-of"


def test_horizontal_falls_back_to_left_when_subject_hugs_right_edge():
    """Subject pushed close to the right side of the 14.2-wide frame leaves
    no room for a `right-of` callout — picker should switch to `left-of`."""
    subject = _rect(6.5, 0.0, w=2.0, h=1.0)
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side == "left-of"


def test_horizontal_falls_back_to_below_when_both_lateral_sides_blocked():
    subject = _rect(0.0, 0.0, w=14.0, h=1.0)  # nearly fills frame width
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side == "below"


# --- vertical preferences -----------------------------------------------


def test_vertical_prefers_below():
    subject = _rect(0.0, 0.0)
    side = pick_subject_side(
        subject, "vertical", callout_size=(3.0, 1.0),
        layout_direction="vertical",
    )
    assert side == "below"


def test_vertical_falls_back_to_above_when_subject_hugs_bottom():
    """Vertical frame is 14.2 tall. Subject at cy=-6.5 with h=1 has no room
    below."""
    subject = _rect(0.0, -6.5, w=2.0, h=1.0)
    side = pick_subject_side(
        subject, "vertical", callout_size=(3.0, 1.0),
        layout_direction="vertical",
    )
    assert side == "above"


# --- always-returns-something fallback ---------------------------------


def test_picker_always_returns_a_known_token():
    """Even when nothing fits, the picker returns the last candidate so
    the caller can still place the callout (it will overflow, validator
    in PR N catches this earlier)."""
    subject = _rect(0.0, 0.0, w=20.0, h=20.0)  # bigger than any frame
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side in ("above", "below", "left-of", "right-of")


# --- parse_subject ------------------------------------------------------


@pytest.mark.parametrize("subject,expected", [
    ("pd",            ("pd", [])),
    ("pd:cell:1,0",   ("pd", ["cell", "1,0"])),
    ("kpis:k-defect", ("kpis", ["k-defect"])),
    ("matrix-1:row:0", ("matrix-1", ["row", "0"])),
])
def test_parse_subject(subject, expected):
    assert parse_subject(subject) == expected


def test_parse_subject_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_subject("")


def test_parse_subject_no_host_raises():
    with pytest.raises(ValueError, match="empty host"):
        parse_subject(":cell:1,0")


# --- resolve_subject_target ---------------------------------------------


def test_resolve_target_bare_id_returns_host():
    pd = _rect(0.0, 0.0)
    out = resolve_subject_target("pd", {"pd": pd})
    assert out is pd


def test_resolve_target_refined_returns_host_too():
    """PR L spec — refined subjects (`pd:cell:1,0`) fall back to the host
    bbox for placement; the leader endpoint is computed separately in
    `position_finalized`."""
    pd = _rect(0.0, 0.0)
    out = resolve_subject_target("pd:cell:1,0", {"pd": pd})
    assert out is pd


def test_resolve_target_unknown_host_raises():
    with pytest.raises(ValueError, match="not in registry"):
        resolve_subject_target("ghost", {"pd": _rect(0, 0)})

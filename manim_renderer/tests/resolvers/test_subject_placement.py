"""PR L / Round 3 — `pick_subject_side` picks the best anchor token.

Contract:
  * Horizontal: prefer `right-of`; fall back to `left-of`. Never crosses
    to above/below (Round 3) — arrows pointing along the layout axis.
  * Vertical: prefer `below`; fall back to `above`. Never crosses to
    right-of/left-of.
  * If neither preferred side fits, return the last candidate (callout
    overflows; validator catches this).
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


def test_horizontal_never_crosses_to_vertical_sides():
    """Round 3: horizontal layouts never fall back to above/below. When
    neither lateral side fits, the picker still returns a lateral
    side (left-of as the last candidate) — the solver clamps. Crossing
    to vertical would fight the layout's reading direction."""
    subject = _rect(0.0, 0.0, w=14.0, h=1.0)  # nearly fills frame width
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side in ("right-of", "left-of")


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
    in PR N catches this earlier). Round 3: only the layout-direction
    candidates are returned."""
    subject = _rect(0.0, 0.0, w=20.0, h=20.0)  # bigger than any frame
    side = pick_subject_side(subject, "horizontal", callout_size=(3.0, 1.0))
    assert side in ("right-of", "left-of")


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

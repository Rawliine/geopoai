"""PR W2 — subject-anchored callouts pack tight with host, group centered.

A callout that uses `params.subject` shares its host's slot. The solver
packs them adjacent with `DEFAULT_ANCHOR_BUFF` gap and centers the pair
in the slot. Both rects use their preferred sizes (clamped if oversize).
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts.base import CastMember
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.resolvers.anchor import DEFAULT_ANCHOR_BUFF


_TOL = 1e-3


def test_lone_primary_owns_slot():
    """Baseline: no callout → lone primary gets the slot rect verbatim
    (PR W2 passthrough)."""
    layout = resolve_layout("hero", "horizontal")
    cast = [
        CastMember(id="host", role="primary", slot="main",
                   preferred_size=(6.0, 3.0)),
    ]
    out = layout.solve(cast)
    assert out["host"] == layout.slots["main"]


def test_subject_callout_packs_tight_horizontal():
    """Horizontal: host on left, callout on right, gap = DEFAULT_ANCHOR_BUFF,
    pair centered in slot."""
    layout = resolve_layout("hero", "horizontal")
    host = CastMember(id="host", role="primary", slot="main",
                      preferred_size=(6.0, 3.0))
    callout = CastMember(id="c", role="annotation", slot="main",
                         preferred_size=(3.0, 1.5),
                         subject_host_id="host")
    out = layout.solve([host, callout])

    assert {"host", "c"} <= set(out)
    h_rect = out["host"]
    c_rect = out["c"]
    # Host is left of callout.
    assert h_rect.cx < c_rect.cx
    # Gap between them equals DEFAULT_ANCHOR_BUFF.
    h_right = h_rect.cx + h_rect.width / 2.0
    c_left = c_rect.cx - c_rect.width / 2.0
    assert c_left - h_right == pytest.approx(DEFAULT_ANCHOR_BUFF, abs=_TOL)
    # Pair is centered around the slot's x center.
    slot = layout.slots["main"]
    pair_center = (
        (h_rect.cx - h_rect.width / 2.0) + (c_rect.cx + c_rect.width / 2.0)
    ) / 2.0
    assert pair_center == pytest.approx(slot.cx, abs=_TOL)
    # Cross-axis: both rects centered on slot center.
    assert h_rect.cy == pytest.approx(slot.cy, abs=_TOL)
    assert c_rect.cy == pytest.approx(slot.cy, abs=_TOL)


def test_subject_callout_packs_tight_vertical():
    """Vertical: host on top, callout on bottom, gap = DEFAULT_ANCHOR_BUFF,
    pair centered in slot."""
    layout = resolve_layout("hero", "vertical")
    host = CastMember(id="host", role="primary", slot="main",
                      preferred_size=(4.0, 6.0))
    callout = CastMember(id="c", role="annotation", slot="main",
                         preferred_size=(3.0, 1.5),
                         subject_host_id="host")
    out = layout.solve([host, callout])

    h_rect = out["host"]
    c_rect = out["c"]
    # Host above callout.
    assert h_rect.cy > c_rect.cy
    # Gap on y axis.
    h_bottom = h_rect.cy - h_rect.height / 2.0
    c_top = c_rect.cy + c_rect.height / 2.0
    assert h_bottom - c_top == pytest.approx(DEFAULT_ANCHOR_BUFF, abs=_TOL)
    # Pair centered on slot's y center.
    slot = layout.slots["main"]
    pair_center = (
        (h_rect.cy + h_rect.height / 2.0) + (c_rect.cy - c_rect.height / 2.0)
    ) / 2.0
    assert pair_center == pytest.approx(slot.cy, abs=_TOL)

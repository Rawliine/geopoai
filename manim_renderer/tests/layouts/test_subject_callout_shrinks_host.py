"""PR W — subject-anchored callouts join the solver cast.

A callout that uses `params.subject` (instead of `params.anchor`) shares
its host's slot in the cast. The solver carves a side region for the
callout and shrinks the host into the remainder.
"""

from __future__ import annotations

import pytest

from manim_renderer.layouts.base import CastMember
from manim_renderer.layouts.resolver import resolve_layout


def test_lone_primary_owns_slot():
    """Baseline: with no callout, the lone primary gets a centered rect
    at its preferred size (no extra reservation)."""
    layout = resolve_layout("hero", "horizontal")
    cast = [
        CastMember(id="host", role="primary", slot="main",
                   preferred_size=(6.0, 3.0)),
    ]
    out = layout.solve(cast)
    slot = layout.slots["main"]
    assert out["host"].cx == pytest.approx(slot.cx)
    assert out["host"].cy == pytest.approx(slot.cy)


def test_subject_callout_reserves_side_region_horizontal():
    """In horizontal format, the subject callout takes the right side;
    the host occupies the left side at reduced width."""
    layout = resolve_layout("hero", "horizontal")
    host = CastMember(id="host", role="primary", slot="main",
                      preferred_size=(6.0, 3.0))
    callout = CastMember(id="c", role="annotation", slot="main",
                         preferred_size=(3.0, 1.5),
                         subject_host_id="host")
    out = layout.solve([host, callout])

    assert "host" in out
    assert "c" in out
    # Callout sits to the right of the host.
    assert out["c"].cx > out["host"].cx
    # Host is centered on the LEFT side of the slot center.
    slot = layout.slots["main"]
    assert out["host"].cx < slot.cx
    # Callout is on the RIGHT side of the slot center.
    assert out["c"].cx > slot.cx


def test_subject_callout_reserves_side_region_vertical():
    """In vertical format, the callout reserves the bottom region."""
    layout = resolve_layout("hero", "vertical")
    host = CastMember(id="host", role="primary", slot="main",
                      preferred_size=(4.0, 6.0))
    callout = CastMember(id="c", role="annotation", slot="main",
                         preferred_size=(3.0, 1.5),
                         subject_host_id="host")
    out = layout.solve([host, callout])

    # Callout sits below the host.
    assert out["c"].cy < out["host"].cy
    slot = layout.slots["main"]
    # Host is above slot center; callout below.
    assert out["host"].cy > slot.cy
    assert out["c"].cy < slot.cy

"""Subject-based placement resolver (Phase 2 / PR L).

Given a subject mobject, the frame bounds, and the layout direction,
pick the best anchor token + buff for a callout that points at the
subject. Replaces the author having to commit to `above:foo` / `below:foo`
upfront — the solver decides which side has room.

Selection rules (current):
  * Horizontal layout: prefer `right-of`. If the subject's right edge is
    too close to the frame's right edge, fall back to `left-of`, then
    `below`, then `above`.
  * Vertical layout: prefer `below`. If the subject's bottom edge is too
    close to the frame's bottom edge, fall back to `above`, then
    `right-of`, then `left-of` (these auto-flip via `resolve_anchor` in
    vertical format, but the solver returns the unflipped token; the
    scene runner's `place_at_anchor` does the flip).

The available space is computed against `FRAME_BOUNDS` (the renderable
area, single source of truth in `layouts/base.py`). Subject bbox is
sampled at call time — restage triggers a re-sample.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from manim_renderer.layouts.base import FRAME_BOUNDS
from manim_renderer.resolvers.anchor import DEFAULT_ANCHOR_BUFF


# Estimated callout footprint. The solver doesn't know the exact callout
# size at placement time (the callout hasn't been measured), so we use a
# conservative envelope. Real measurements come from
# `CalloutBox.measure(params, format)` once the runner instantiates it.
_DEFAULT_CALLOUT_W = 4.5
_DEFAULT_CALLOUT_H = 1.5


def _frame_rect(format: str) -> tuple[float, float]:
    return FRAME_BOUNDS.get(format, FRAME_BOUNDS["horizontal"])


def _fits(side: str, subject_bbox: tuple[float, float, float, float],
          callout_size: tuple[float, float], frame: tuple[float, float],
          buff: float) -> bool:
    """Does a callout of `callout_size` fit on `side` of `subject_bbox`
    within `frame`?

    subject_bbox is (left, right, top, bottom) in scene coords.
    """
    left, right, top, bottom = subject_bbox
    fw, fh = frame
    cw, ch = callout_size

    if side == "right-of":
        return right + buff + cw <= fw / 2.0
    if side == "left-of":
        return left - buff - cw >= -fw / 2.0
    if side == "above":
        return top + buff + ch <= fh / 2.0
    if side == "below":
        return bottom - buff - ch >= -fh / 2.0
    return False


def pick_subject_side(
    subject_mob,
    format: str,
    callout_size: tuple[float, float] | None = None,
    *,
    layout_direction: str = "horizontal",
    buff: float = DEFAULT_ANCHOR_BUFF,
    candidate_order: Iterable[str] | None = None,
) -> str:
    """Return the best anchor token for a callout pointing at `subject_mob`.

    Args:
        subject_mob: any Manim mobject with `get_left/right/top/bottom`.
        format: scene format (drives FRAME_BOUNDS lookup).
        callout_size: optional (w, h) hint. Defaults to a conservative
            envelope. Pass the real measurement when available.
        layout_direction: `"horizontal"` (default) prefers right-of/left-of;
            `"vertical"` prefers below/above.
        buff: spacing between subject and callout (Manim units).
        candidate_order: override the preference list. The first side that
            fits wins. The last entry is the unconditional fallback.

    Returns:
        One of `"above"`, `"below"`, `"left-of"`, `"right-of"`. Note: the
        scene runner applies the vertical auto-flip via `place_at_anchor`;
        the picker stays unflipped.
    """
    if callout_size is None:
        callout_size = (_DEFAULT_CALLOUT_W, _DEFAULT_CALLOUT_H)

    bbox = (
        float(subject_mob.get_left()[0]),
        float(subject_mob.get_right()[0]),
        float(subject_mob.get_top()[1]),
        float(subject_mob.get_bottom()[1]),
    )
    frame = _frame_rect(format)

    if candidate_order is None:
        if layout_direction == "vertical":
            order = ("below", "above", "right-of", "left-of")
        else:
            order = ("right-of", "left-of", "below", "above")
    else:
        order = tuple(candidate_order)

    for side in order:
        if _fits(side, bbox, callout_size, frame, buff):
            return side
    # Last resort: the final candidate, even if it overflows.
    return order[-1]


def parse_subject(subject: str) -> tuple[str, list[str]]:
    """Split a subject string into (host_id, refinement_path).

    Examples:
        "pd"            -> ("pd", [])
        "pd:cell:1,0"   -> ("pd", ["cell", "1,0"])
        "kpis:k-defect" -> ("kpis", ["k-defect"])

    The refinement path is consumed by `resolve_subject_target` to walk
    custom anchors on the host component.
    """
    if not subject:
        raise ValueError("subject string is empty")
    head, _, tail = subject.partition(":")
    if not head:
        raise ValueError(f"subject {subject!r} has empty host id")
    parts = [p for p in tail.split(":") if p] if tail else []
    return head, parts


def resolve_subject_target(subject: str, id_to_mobject: dict):
    """Look up the mobject a subject string points at.

    For a bare id (`"pd"`) returns the registered mobject. For a refined
    subject (`"pd:cell:1,0"`) returns the result of
    `host.get_anchor("cell:1,0")`'s underlying mobject if available, else
    falls back to the host (the host bbox is a reasonable approximation).

    The returned object must support `get_left/right/top/bottom` — i.e. be
    a Manim mobject or any duck-typed equivalent.
    """
    host_id, parts = parse_subject(subject)
    host = id_to_mobject.get(host_id)
    if host is None:
        raise ValueError(
            f"subject {subject!r}: host id {host_id!r} not in registry "
            f"(known: {sorted(id_to_mobject)})"
        )
    if not parts:
        return host
    # Re-join the refinement parts into a custom anchor token and ask the
    # host. The host's `get_anchor` returns a point, not a mobject — but
    # the picker only needs bbox-style accessors. We return the host as a
    # fallback "good enough" bbox source; the actual leader endpoint is
    # drawn from `resolve_anchor` in `position_finalized`.
    return host

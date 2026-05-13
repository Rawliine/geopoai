"""Anchor resolver — turn an anchor string into a Manim coord.

Tokens (Phase 1, locked):
  * `above:id`     — directly above target, with `padding` gap
  * `below:id`     — directly below target, with `padding` gap
  * `left-of:id`   — to the left of target, with `padding` gap
  * `right-of:id`  — to the right of target, with `padding` gap
  * `inside:id`    — at target's bounding-box center (overlays on top)

Format auto-flip (recap.md §7):
  In `vertical` format, `right-of` -> `below`, `left-of` -> `above` unless the
  caller passes `strict_axis=True`. Components and JSON authors stay axis-agnostic.

Coord sampling rule (recap.md §6):
  The anchor coord is sampled at *call time* from the target's *current* state.
  If the target is animating when an anchored event fires, the anchor sees the
  target where it is at that frame. Documented in AGENT.md rule 9.
"""

from __future__ import annotations

import numpy as np

# All five tokens supported by the resolver. The schema's anchor_string regex
# must stay in sync.
ANCHOR_TOKENS: tuple[str, ...] = (
    "above",
    "below",
    "left-of",
    "right-of",
    "inside",
)

# In vertical format, lateral tokens flip to vertical equivalents.
_VERTICAL_FLIP = {
    "right-of": "below",
    "left-of": "above",
}

# Unit-vector for each token (None for `inside`, which overlays at center).
# Used by `place_at_anchor` to drive Manim's next_to.
_ANCHOR_DIRECTION = {
    "above":    np.array([0.0,  1.0, 0.0]),
    "below":    np.array([0.0, -1.0, 0.0]),
    "left-of":  np.array([-1.0, 0.0, 0.0]),
    "right-of": np.array([1.0,  0.0, 0.0]),
    "inside":   None,
}

# Default gap between an anchored component and its target. Small enough that
# the components feel related, large enough that any leader line drawn between
# them (e.g. CalloutBox's arrow) is visibly outside both bounding boxes.
DEFAULT_ANCHOR_BUFF = 0.5


def parse_anchor(anchor: str) -> tuple[str, str]:
    """Split `'<token>:<id>'` -> `(token, id)`. Raises ValueError on bad input."""
    if ":" not in anchor:
        raise ValueError(
            f"anchor {anchor!r} missing ':' separator; expected '<token>:<id>'"
        )
    token, _, ident = anchor.partition(":")
    if token not in ANCHOR_TOKENS:
        raise ValueError(
            f"anchor token {token!r} not in {ANCHOR_TOKENS}"
        )
    if not ident:
        raise ValueError(f"anchor {anchor!r} has empty id after ':'")
    return token, ident


def resolve_anchor(
    anchor: str,
    id_to_mobject: dict,
    format: str,
    padding: float = 0.3,
    *,
    strict_axis: bool = False,
) -> np.ndarray:
    """Resolve an anchor string to an (x, y, 0) Manim coord.

    Args:
        anchor: e.g. `"below:tree-1"`.
        id_to_mobject: scene's id-registry of currently-positioned mobjects.
        format: `"horizontal"` or `"vertical"`.
        padding: gap (in Manim units) between the anchor point and the target's edge.
        strict_axis: if True, do not auto-flip lateral tokens in vertical format.

    Returns:
        np.ndarray shape (3,) — the resolved (x, y, 0) point.

    Raises:
        ValueError: on malformed anchor string or unknown id.
    """
    token, ident = parse_anchor(anchor)
    target = id_to_mobject.get(ident)
    if target is None:
        raise ValueError(
            f"anchor {anchor!r}: id {ident!r} not in id registry "
            f"(known: {sorted(id_to_mobject)})"
        )

    if format == "vertical" and not strict_axis:
        token = _VERTICAL_FLIP.get(token, token)

    if token == "inside":
        return np.asarray(target.get_center(), dtype=float)
    if token == "above":
        edge = np.asarray(target.get_top(), dtype=float)
        return edge + np.array([0.0, padding, 0.0])
    if token == "below":
        edge = np.asarray(target.get_bottom(), dtype=float)
        return edge + np.array([0.0, -padding, 0.0])
    if token == "right-of":
        edge = np.asarray(target.get_right(), dtype=float)
        return edge + np.array([padding, 0.0, 0.0])
    if token == "left-of":
        edge = np.asarray(target.get_left(), dtype=float)
        return edge + np.array([-padding, 0.0, 0.0])
    # Defense in depth — parse_anchor should have caught this.
    raise ValueError(f"anchor token {token!r} unhandled (after format flip)")


def place_at_anchor(
    component,
    target,
    anchor: str,
    format: str,
    *,
    buff: float = DEFAULT_ANCHOR_BUFF,
    strict_axis: bool = False,
) -> None:
    """Position `component` adjacent to `target` per the anchor token, using
    Manim's `next_to` so the appropriate edge of `component` sits at `buff`
    units from the matching edge of `target` — no overlap.

    Use this in the scene runner instead of `resolve_anchor + move_to`. The
    coord-returning `resolve_anchor` is kept for callers that need a literal
    point (e.g. drawing a line endpoint), not for placing a sized component.

    For `inside:`, places `component` at `target`'s center (overlay).

    In vertical format, lateral tokens (`right-of`, `left-of`) auto-flip to
    `below`/`above`, mirroring `resolve_anchor`. Pass `strict_axis=True` to
    disable.
    """
    token, _ = parse_anchor(anchor)
    if format == "vertical" and not strict_axis:
        token = _VERTICAL_FLIP.get(token, token)
    direction = _ANCHOR_DIRECTION[token]
    if direction is None:
        component.move_to(target.get_center())
    else:
        component.next_to(target, direction, buff=buff)

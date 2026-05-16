"""bestResponseArrow — draw an arrow between two PayoffMatrix cells.

JSON shape:
    { "at": 9.0, "action": "bestResponseArrow",
      "params": { "target": "matrix-1", "from": [0,0], "to": [0,1],
                  "actor": "actor_a" } }

Used to visualize a player's best response — "if opponent plays X, my best
response is Y." Colored by the `actor` palette key so multiple arrows for
different players read clearly.

Returns a `Create(arrow)` Animation. The arrow is straight; future PRs can
add curve options if needed.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from manim import Animation, Arrow, Create

from manim_renderer.actions._context import ActionContext
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import TIMING


_PALETTE = {**ACTORS, **SEMANTIC, **UI}


def best_response_arrow(ctx: ActionContext) -> Optional[Animation]:
    target_id = ctx.params.get("target")
    if not target_id:
        raise ValueError("bestResponseArrow requires params.target")
    target = ctx.id_to_mobject.get(target_id)
    if target is None:
        raise ValueError(
            f"bestResponseArrow: target {target_id!r} not in id registry "
            f"(known: {sorted(ctx.id_to_mobject)})"
        )
    if not hasattr(target, "cell_dims"):
        raise ValueError(
            f"bestResponseArrow target {target_id!r} is not a "
            f"PayoffMatrix-shaped component"
        )

    src = ctx.params.get("from")
    dst = ctx.params.get("to")
    if not (isinstance(src, list) and isinstance(dst, list)
            and len(src) == 2 and len(dst) == 2):
        raise ValueError(
            "bestResponseArrow requires params.from and params.to as [row, col]"
        )

    actor = ctx.params.get("actor", "actor_a")
    if actor not in _PALETTE:
        raise ValueError(
            f"bestResponseArrow actor {actor!r} not in palette; "
            f"available: {sorted(_PALETTE)}"
        )
    hex_color = _PALETTE[actor]

    timing = ctx.params.get("timing", "normal")
    run_time = TIMING[timing]

    def _build(host) -> Arrow:
        start = np.asarray(host.get_anchor(f"cell:{int(src[0])},{int(src[1])}"))
        end = np.asarray(host.get_anchor(f"cell:{int(dst[0])},{int(dst[1])}"))
        return Arrow(
            start=start,
            end=end,
            color=hex_color,
            stroke_width=4.0,
            buff=0.35,
            max_tip_length_to_length_ratio=0.18,
        )

    arrow = _build(target)
    ctx.register_overlay(
        target_id, arrow,
        overlay_id=ctx.params.get("id"),
        rebuild=_build,
    )
    return Create(arrow, run_time=run_time)

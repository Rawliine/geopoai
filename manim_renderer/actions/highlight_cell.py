"""highlightCell — emphasize a PayoffMatrix cell with a colored overlay.

JSON shape:
    { "at": 6.0, "action": "highlightCell",
      "params": { "target": "matrix-1", "index": [1, 1], "color": "highlight" } }

`index` is `[row, col]`, 0-based. `color` defaults to `highlight` (palette yellow).

Returns a `FadeIn(overlay)` Animation. The overlay is a translucent rectangle
matching the cell's dimensions, layered on top of the existing cell. It is
NOT registered in `id_to_mobject` — it's ephemeral. To remove a highlight,
use a follow-up `highlightCell` with a contrasting color, or add a `clearHighlights`
action in a future PR.

Phase 1 limitation: overlays cannot be removed via `removeComponent` because
they have no id. Documented in handoff.md.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from manim import Animation, FadeIn, Rectangle

from manim_renderer.actions._context import ActionContext
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import TIMING


_PALETTE = {**ACTORS, **SEMANTIC, **UI}


def highlight_cell(ctx: ActionContext) -> Optional[Animation]:
    target_id = ctx.params.get("target")
    if not target_id:
        raise ValueError("highlightCell requires params.target")
    target = ctx.id_to_mobject.get(target_id)
    if target is None:
        raise ValueError(
            f"highlightCell: target {target_id!r} not in id registry "
            f"(known: {sorted(ctx.id_to_mobject)})"
        )

    index = ctx.params.get("index")
    if not isinstance(index, list) or len(index) != 2:
        raise ValueError("highlightCell requires params.index = [row, col]")
    i, j = int(index[0]), int(index[1])

    color_key = ctx.params.get("color", "highlight")
    if color_key not in _PALETTE:
        raise ValueError(
            f"highlightCell color {color_key!r} not in palette; "
            f"available: {sorted(_PALETTE)}"
        )
    hex_color = _PALETTE[color_key]

    timing = ctx.params.get("timing", "fast")
    run_time = TIMING[timing]

    # cell_dims() is part of the PayoffMatrix public surface; if the target
    # isn't a PayoffMatrix, this fails loudly with a clear AttributeError.
    if not hasattr(target, "cell_dims"):
        raise ValueError(
            f"highlightCell target {target_id!r} is not a PayoffMatrix-shaped "
            f"component (missing cell_dims/get_anchor); got {type(target).__name__}"
        )

    cell_center = target.get_anchor(f"cell:{i},{j}")
    cell_w, cell_h = target.cell_dims()

    overlay = Rectangle(
        width=cell_w,
        height=cell_h,
        color=hex_color,
        stroke_width=3.0,
        fill_color=hex_color,
        fill_opacity=0.30,
    )
    overlay.move_to(np.asarray(cell_center))
    # Phase 1.5: track overlay against host so removeComponent cleans it.
    # Optional `id` exposes the overlay as a top-level id (3b).
    ctx.register_overlay(target_id, overlay, overlay_id=ctx.params.get("id"))
    return FadeIn(overlay, run_time=run_time)

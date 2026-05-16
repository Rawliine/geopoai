"""crossOut — strike through a PayoffMatrix row or column (IESDS visual).

JSON shape:
    { "at": 8.0, "action": "crossOut",
      "params": { "target": "matrix-1", "axis": "row", "index": 0, "style": "strike" } }

`axis` is `"row"` or `"col"`. `index` is 0-based. `style` is:
  * `strike` — straight line through the band (default)
  * `dashed` — same path but with a dashed stroke

Returns a `Create(line)` Animation drawing the line. Used for iterated
elimination of strictly dominated strategies (IESDS) in game-theory videos.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from manim import Animation, Create, DashedLine, Line

from manim_renderer.actions._context import ActionContext
from manim_renderer.theme.palette import SEMANTIC
from manim_renderer.theme.timing import TIMING


_STROKE_WIDTH = 4.0


def cross_out(ctx: ActionContext) -> Optional[Animation]:
    target_id = ctx.params.get("target")
    if not target_id:
        raise ValueError("crossOut requires params.target")
    target = ctx.id_to_mobject.get(target_id)
    if target is None:
        raise ValueError(
            f"crossOut: target {target_id!r} not in id registry "
            f"(known: {sorted(ctx.id_to_mobject)})"
        )
    if not hasattr(target, "cell_dims"):
        raise ValueError(
            f"crossOut target {target_id!r} is not a PayoffMatrix-shaped component"
        )

    axis = ctx.params.get("axis")
    if axis not in ("row", "col"):
        raise ValueError(f"crossOut axis must be 'row' or 'col'; got {axis!r}")
    index = ctx.params.get("index")
    if index is None:
        raise ValueError("crossOut requires params.index")
    idx = int(index)

    style = ctx.params.get("style", "strike")
    if style not in ("strike", "dashed"):
        raise ValueError(f"crossOut style must be 'strike' or 'dashed'; got {style!r}")

    timing = ctx.params.get("timing", "normal")
    run_time = TIMING[timing]

    color = SEMANTIC["negative"]
    cls = DashedLine if style == "dashed" else Line

    def _build(host):
        cell_w, cell_h = host.cell_dims()
        if axis == "row":
            n = host.n_cols()
            left = host.get_anchor(f"cell:{idx},0")
            right = host.get_anchor(f"cell:{idx},{n - 1}")
            start = np.asarray(left) + np.array([-cell_w / 2 * 0.95, 0.0, 0.0])
            end = np.asarray(right) + np.array([+cell_w / 2 * 0.95, 0.0, 0.0])
        else:
            n = host.n_rows()
            top = host.get_anchor(f"cell:0,{idx}")
            bottom = host.get_anchor(f"cell:{n - 1},{idx}")
            start = np.asarray(top) + np.array([0.0, +cell_h / 2 * 0.95, 0.0])
            end = np.asarray(bottom) + np.array([0.0, -cell_h / 2 * 0.95, 0.0])
        return cls(start=start, end=end, color=color, stroke_width=_STROKE_WIDTH)

    line = _build(target)
    ctx.register_overlay(
        target_id, line,
        overlay_id=ctx.params.get("id"),
        rebuild=_build,
    )
    return Create(line, run_time=run_time)

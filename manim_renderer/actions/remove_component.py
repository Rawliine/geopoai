"""removeComponent action — fade/dissolve an existing component out and unregister it.

JSON shape:
    { "at": 8.0, "action": "removeComponent",
      "params": { "target": "matrix-1", "effect": "fade-out", "timing": "fast" } }

Default effect: `fade-out`. Default timing: `fast`. Both override-able from JSON.
"""

from __future__ import annotations

from typing import Optional

from manim import Animation

from manim_renderer.actions._context import ActionContext
from manim_renderer.effects.exits import get_exit


def remove_component(ctx: ActionContext) -> Optional[Animation]:
    target_id = ctx.params.get("target")
    if not target_id:
        raise ValueError("removeComponent requires params.target")
    mob = ctx.id_to_mobject.get(target_id)
    if mob is None:
        raise ValueError(
            f"removeComponent: target {target_id!r} not in id registry "
            f"(known: {sorted(ctx.id_to_mobject)})"
        )

    effect = ctx.params.get("effect", "fade-out")
    timing = ctx.params.get("timing", "fast")
    anim = get_exit(effect, mob, timing)

    # Drop from registry so subsequent anchor lookups fail cleanly rather than
    # pointing at a faded-out ghost.
    del ctx.id_to_mobject[target_id]
    return anim

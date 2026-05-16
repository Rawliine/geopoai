"""removeComponent action — fade/dissolve an existing component out and unregister it.

JSON shape:
    { "at": 8.0, "action": "removeComponent",
      "params": { "target": "matrix-1", "effect": "fade-out", "timing": "fast" } }

Default effect: `fade-out`. Default timing: `fast`. Both override-able from JSON.

Phase 1.5 — overlay cleanup:
  If the target has overlays registered against it in
  `scene._overlays_by_host[target]`, all overlays fade out in parallel with
  the host. Overlay ids (if any) are dropped from `id_to_mobject`.
"""

from __future__ import annotations

from typing import Optional

from manim import Animation, AnimationGroup, FadeOut

from manim_renderer.actions._context import ActionContext
from manim_renderer.effects.exits import get_exit
from manim_renderer.theme.timing import TIMING


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
    host_anim = get_exit(effect, mob, timing)

    # Drop the host id first so subsequent anchor lookups fail cleanly.
    del ctx.id_to_mobject[target_id]
    # Keep Phase 2 solver state in sync — missing keys are fine for stubs.
    for attr in (
        "_roles", "_id_to_slot", "_params_by_id", "_class_by_id",
        "_restage_base_size", "_subject_host_by_id",
        "_slot_origin_by_id",
    ):
        bookkeeping = getattr(ctx.scene, attr, None)
        if bookkeeping is not None:
            bookkeeping.pop(target_id, None)

    # Pull any overlays registered against this host. The scene may not
    # have the attribute if the action was invoked from a unit test that
    # didn't initialize JSONScene; treat as "no overlays".
    overlays_map = getattr(ctx.scene, "_overlays_by_host", None) or {}
    overlays = overlays_map.pop(target_id, [])
    if not overlays:
        return host_anim

    # Drop any id-bearing overlays from id_to_mobject too. We walk the dict
    # because overlay ids aren't stored back-referenced — cheap given typical
    # registry sizes (<100 entries).
    for ov in overlays:
        for ident, registered in list(ctx.id_to_mobject.items()):
            if registered is ov:
                del ctx.id_to_mobject[ident]

    overlay_run_time = TIMING[timing]
    overlay_anims = [FadeOut(ov, run_time=overlay_run_time) for ov in overlays]
    return AnimationGroup(host_anim, *overlay_anims)

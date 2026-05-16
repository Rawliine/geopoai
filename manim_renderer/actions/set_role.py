"""setRole action — change the role of an existing component.

PR F (this file): records the new role in `scene._roles[target]` and returns
None. No animation, no movement. The restage pass that consumes the new role
ships in PR G.

JSON shape:
    { "at": 12.0, "action": "setRole",
      "params": { "target": "matrix-1", "role": "supporting", "timing": "fast" } }

The `timing` param is reserved for PR G — once `_restage` builds Transform
animations, this is the run_time those animations use. PR F ignores it.

Validator coverage:
  * Tier 2 (action-params): schema/action_schemas/set_role.json enforces
    required target + role and the role_name enum.
  * Tier 4 (anchors): `target` is in `_ID_REF_PARAM_KEYS`, so the validator
    already rejects setRole against an unknown id.
"""

from __future__ import annotations

from typing import Optional

from manim import Animation

from manim_renderer.actions._context import ActionContext


def set_role(ctx: ActionContext) -> Optional[Animation]:
    target_id = ctx.params.get("target")
    if not target_id:
        raise ValueError("setRole requires params.target")
    role = ctx.params.get("role")
    if not role:
        raise ValueError("setRole requires params.role")
    if target_id not in ctx.id_to_mobject:
        raise ValueError(
            f"setRole: target {target_id!r} not in id registry "
            f"(known: {sorted(ctx.id_to_mobject)})"
        )

    # Record on scene. Tolerate scene=None (unit tests exercising the callable
    # without a JSONScene), matching the same convention as register_overlay.
    if ctx.scene is not None:
        if not hasattr(ctx.scene, "_roles"):
            ctx.scene._roles = {}
        ctx.scene._roles[target_id] = role

    # Keep the component's own attribute in sync so any code that reads
    # `mob.role` after a setRole sees the new value.
    mob = ctx.id_to_mobject[target_id]
    if hasattr(mob, "role"):
        mob.role = role

    # no animation. adds restage.
    return None

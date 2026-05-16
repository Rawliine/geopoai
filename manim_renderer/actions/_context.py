"""ActionContext — argument bundle passed to every ACTION_REGISTRY callable.

Action callables have the shape:
    (ctx: ActionContext) -> Animation | None

They mutate or remove existing scene mobjects. They do NOT instantiate new
components — that's the COMPONENT_REGISTRY's job. Phase 2's camera actions
plug into this same shape.

Overlay tracking (Phase 1.5):
  Mutation actions that produce overlays (highlightCell, crossOut,
  bestResponseArrow) call `ctx.register_overlay(host_id, mob, overlay_id=...)`
  after constructing their overlay. The overlay is recorded in
  `scene._overlays_by_host` so `removeComponent` can fade host + overlays
  together. If `overlay_id` is provided, the overlay is also exposed in
  `id_to_mobject` so it can be `removeComponent`'d on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from manim import Mobject, MovingCameraScene


@dataclass
class ActionContext:
    params: dict
    id_to_mobject: dict[str, Any]
    format: str
    scene: "MovingCameraScene"  # access to camera, etc. (Phase 2 uses this)

    def register_overlay(
        self,
        host_id: str,
        mob: Any,
        overlay_id: str | None = None,
        *,
        rebuild: Optional[Callable[["Mobject"], "Mobject"]] = None,
    ) -> None:
        """Track `mob` as an overlay against `host_id`.

        The overlay is added to `scene._overlays_by_host[host_id]` so a
        future `removeComponent(target=host_id)` fades it with the host. If
        `overlay_id` is provided, the overlay is ALSO added to `id_to_mobject`
        so it can be targeted directly by `removeComponent`. Auto-cleanup
        still applies — removing the host removes all its overlays even if
        they had ids.

        `rebuild` is an optional callable that, given a host mobject at
        a target state, returns a freshly-constructed overlay positioned
        against that target state. The scene runner uses it during
        restage to Transform the overlay smoothly into its new geometry
        — important for shapes like arrows whose tip rendering doesn't
        scale linearly under Manim's `.animate.scale`. Overlays without
        a rebuild fall back to a scale+shift walker around the host's
        current center.

        Raises ValueError on overlay-id collision with an existing id (the
        validator should catch this earlier via `_ACTION_ID_EXTRACTORS`).
        """
        if rebuild is not None:
            # Attach the recipe directly to the mobject so the runner can
            # find it via `getattr(overlay, "_rebuild_recipe", None)`.
            mob._rebuild_recipe = rebuild
        # `scene` may be None in unit tests that exercise an action callable
        # without a JSONScene runner — skip registration in that case but
        # still honor the opt-in id below so id-collision tests work.
        if self.scene is not None:
            if not hasattr(self.scene, "_overlays_by_host"):
                self.scene._overlays_by_host = {}
            self.scene._overlays_by_host.setdefault(host_id, []).append(mob)
        if overlay_id is not None:
            if overlay_id in self.id_to_mobject:
                raise ValueError(
                    f"overlay id {overlay_id!r} collides with an existing id "
                    f"(known: {sorted(self.id_to_mobject)}); ids must be unique"
                )
            self.id_to_mobject[overlay_id] = mob

"""JSONScene — the Manim runner that interprets a validated scene dict.

Event ordering (locked):
  Events from `slots`, `overlays`, and `timeline` merge into one list sorted by
  `(at, phase)` where phase is `slots=0, overlays=1, timeline=2`. At equal `at`,
  slot components are instantiated before overlays — guaranteeing that overlay
  anchors can resolve against slot ids that fired the same instant.

Two-registry dispatch:
  * COMPONENT_REGISTRY -> instantiate, position via slot or anchor, register id,
    play entrance.
  * ACTION_REGISTRY    -> mutate or remove existing mobjects via callable.

Cursor advancement:
  Both registries advance `cursor` by the played animation's run_time. Two
  events at the same `at` therefore play sequentially in phase order.
"""

from __future__ import annotations

from manim import MovingCameraScene

from manim_renderer.actions import ActionContext
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY
from manim_renderer.resolvers.anchor import resolve_anchor
from manim_renderer.resolvers.size import resolve_size

# Phase ordering for sort tiebreaks at the same `at`.
_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2


class JSONScene(MovingCameraScene):
    """Class attribute scene_data is set by the wrapper before render()."""

    scene_data: dict = {}

    def construct(self):
        scene = self.scene_data
        fmt = scene.get("format", "horizontal")
        duration = float(scene.get("scene", {}).get("duration", 0.0))
        layout_name = scene.get("scene", {}).get("layout", "hero")

        self._layout = resolve_layout(layout_name, fmt)
        self._id_to_mobject: dict = {}

        events = self._collect_events(scene)

        cursor = 0.0
        for slot_name, _phase, ev in events:
            at = float(ev["at"])
            if at > cursor:
                self.wait(at - cursor)
                cursor = at

            action = ev["action"]
            params = ev.get("params") or {}

            if action in COMPONENT_REGISTRY:
                anim = self._dispatch_component(
                    action, params, slot_name, fmt
                )
            elif action in ACTION_REGISTRY:
                anim = self._dispatch_action(action, params, fmt)
            else:
                raise ValueError(
                    f"unknown action {action!r}; "
                    f"components: {sorted(COMPONENT_REGISTRY)}, "
                    f"actions: {sorted(ACTION_REGISTRY)}"
                )

            if anim is not None:
                self.play(anim)
                cursor = at + (anim.run_time or 0.0)

        if duration > cursor:
            self.wait(duration - cursor)

    # --- dispatch ------------------------------------------------------------

    def _dispatch_component(
        self,
        action: str,
        params: dict,
        slot_name: str | None,
        fmt: str,
    ):
        ComponentCls = COMPONENT_REGISTRY[action]

        # Optional size resolution — components that take dims handle them
        # via params; we surface resolved dims as `_resolved_size` for use
        # in build(). Components without a size param ignore.
        size_role = params.get("size")
        if isinstance(size_role, str):
            kind = params.get("size_kind", "default")
            params = {**params, "_resolved_size": resolve_size(size_role, fmt, kind)}

        component = ComponentCls(params, format=fmt)

        # Position: slot wins if both slot and anchor are present (slots are the
        # primary composition layer; anchors are for overlays). Anchor only
        # applies when slot_name is None.
        anchor = params.get("anchor")
        if slot_name is not None:
            rect = self._layout.slot(slot_name)
            component.move_to(rect.center)
        elif anchor:
            coord = resolve_anchor(anchor, self._id_to_mobject, fmt)
            component.move_to(coord)

        # Defense in depth: validator already rejects duplicate ids. Assert here
        # so a bypass during dev fails loudly rather than silently overwriting.
        if component.id:
            assert component.id not in self._id_to_mobject, (
                f"duplicate id {component.id!r} reached scene runner; "
                f"validator should have caught this"
            )
            self._id_to_mobject[component.id] = component

        return component.entrance(
            params.get("effect", "fade-in"),
            params.get("timing", "normal"),
        )

    def _dispatch_action(self, action: str, params: dict, fmt: str):
        callable_ = ACTION_REGISTRY[action]
        ctx = ActionContext(
            params=params,
            id_to_mobject=self._id_to_mobject,
            format=fmt,
            scene=self,
        )
        return callable_(ctx)

    # --- event collection ----------------------------------------------------

    @staticmethod
    def _collect_events(scene: dict) -> list[tuple[str | None, int, dict]]:
        """Yield (slot_name_or_None, phase, event) tuples sorted by (at, phase).

        Phase guarantees that at equal `at`, slots fire before overlays before
        timeline. Validator's `validate_anchors` walks events in this same order.
        """
        events: list[tuple[str | None, int, dict]] = []
        for slot_name, ev in (scene.get("slots") or {}).items():
            events.append((slot_name, _PHASE_SLOT, ev))
        for ev in scene.get("overlays") or []:
            events.append((None, _PHASE_OVERLAY, ev))
        for ev in scene.get("timeline") or []:
            events.append((None, _PHASE_TIMELINE, ev))
        events.sort(
            key=lambda triple: (float(triple[2].get("at", 0.0)), triple[1])
        )
        return events

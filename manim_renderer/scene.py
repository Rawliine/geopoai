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
from manim_renderer.resolvers.anchor import parse_anchor, place_at_anchor

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

        # Components that consume sizes call `resolve_size` themselves in
        # build(). The scene runner doesn't pre-resolve — `params.size` means
        # different things in different schemas (typography role for TextCard,
        # resolve_size role for charts).

        # Slot-bounds hint: when a component is placed in a slot, expose the
        # slot's (width, height) so text-bearing components can auto-fit. Pass
        # via params with a leading-underscore key to mark it as internal
        # (validator runs before this; it never sees `_slot_bounds`).
        slot_rect = self._layout.slot(slot_name) if slot_name is not None else None
        if slot_rect is not None:
            params = {**params, "_slot_bounds": (slot_rect.width, slot_rect.height)}

        component = ComponentCls(params, format=fmt)

        # Position: slot wins if both slot and anchor are present (slots are the
        # primary composition layer; anchors are for overlays). Anchor only
        # applies when slot_name is None.
        #
        # For anchored placement we use `place_at_anchor` (next_to-based) so the
        # component's edge sits at the target's edge with a clean buff gap —
        # NOT `resolve_anchor + move_to`, which centers the component at the
        # target edge and causes overlap (the component extends half its size
        # back into the target).
        anchor = params.get("anchor")
        anchor_target = None
        if slot_rect is not None:
            component.move_to(slot_rect.center)
        elif anchor:
            _, target_id = parse_anchor(anchor)
            anchor_target = self._id_to_mobject.get(target_id)
            if anchor_target is None:
                raise ValueError(
                    f"anchor {anchor!r}: target id {target_id!r} not in "
                    f"registry (validator should have caught this)"
                )
            place_at_anchor(component, anchor_target, anchor, fmt)

        # Defense in depth: validator already rejects duplicate ids. Assert here
        # so a bypass during dev fails loudly rather than silently overwriting.
        if component.id:
            assert component.id not in self._id_to_mobject, (
                f"duplicate id {component.id!r} reached scene runner; "
                f"validator should have caught this"
            )
            self._id_to_mobject[component.id] = component

        # Merge child-component ids the parent exposes (e.g. MetricGroup's
        # named stats). Same duplicate guard applies — collisions either with
        # the parent or with existing ids fail loudly.
        for child_id, child_mob in component.extra_id_registrations().items():
            assert child_id not in self._id_to_mobject, (
                f"duplicate id {child_id!r} from {component.__class__.__name__}."
                f"extra_id_registrations() reached scene runner; "
                f"validator should have caught this"
            )
            self._id_to_mobject[child_id] = child_mob

        # Post-positioning hook — components like CalloutBox use this to
        # add a leader line whose endpoint depends on absolute coords.
        component.position_finalized(
            anchor=anchor,
            target=anchor_target,
            format=fmt,
        )

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

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

Restage (Phase 2 / PR G+):
  After every composition change (show, removeComponent, setRole) the runner
  calls `_restage(reason)`. The pass captures the live cast's current state,
  asks `_compute_target_rects` for new positions/sizes, and Transforms anything
  that moved. Mutations (highlightCell, crossOut, bestResponseArrow) do NOT
  trigger restage; their overlays follow the host via the parallel walker over
  `_overlays_by_host`. In PR G the planner returns identity, so no movement
  actually happens — this PR just wires the trigger points.
"""

from __future__ import annotations

import numpy as np
from manim import AnimationGroup, MovingCameraScene

from manim_renderer.actions import ActionContext
from manim_renderer.layouts.base import CastMember, Rect
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY
from manim_renderer.resolvers.anchor import parse_anchor, place_at_anchor
from manim_renderer.theme.timing import TIMING

# Phase ordering for sort tiebreaks at the same `at`.
_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2

# Actions that change composition and therefore trigger a restage pass.
# Mutations (highlightCell, crossOut, bestResponseArrow) are deliberately
# absent — overlays follow their host via the parallel walker, not a fresh
# layout solve.
_RESTAGE_AFTER_ACTIONS = {"removeComponent", "setRole"}

# How close two positions need to be before we treat a restage delta as
# "didn't move" (skip Transform). Absolute units, matches Manim defaults.
_RESTAGE_POS_TOL = 1e-4


class JSONScene(MovingCameraScene):
    """Class attribute scene_data is set by the wrapper before render()."""

    scene_data: dict = {}

    def construct(self):
        scene = self.scene_data
        fmt = scene.get("format", "horizontal")
        duration = float(scene.get("scene", {}).get("duration", 0.0))
        layout_name = scene.get("scene", {}).get("layout", "hero")

        self._layout = resolve_layout(layout_name, fmt)
        self._format = fmt
        self._id_to_mobject: dict = {}
        # Overlay tracking (Phase 1.5): mutation actions register overlays
        # against their host id here; `removeComponent` consumes the list to
        # fade host + overlays together. See `actions/_context.py`.
        self._overlays_by_host: dict[str, list] = {}
        # Role tracking (Phase 2 / PR F): every show action seeds an entry
        # here; `setRole` mutates it. Drives the restage pass (PR G+).
        self._roles: dict[str, str] = {}
        # PR J — per-id solver inputs. Used by `_cast()` to ask each
        # component class for `preferred_size(params, fmt, role)` on every
        # restage. Updated on show; entries dropped on remove.
        self._id_to_slot: dict[str, str | None] = {}
        self._params_by_id: dict[str, dict] = {}
        self._class_by_id: dict[str, type] = {}
        # Last-seen restage state for diagnostics. Map id -> (center, scale).
        self._restage_state: dict[str, tuple[np.ndarray, float]] = {}

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

            # Restage hook (Phase 2 / PR G). Every show-action and every
            # composition-changing action fires a pass. Mutations are quiet.
            timing = params.get("timing", "normal")
            if action in COMPONENT_REGISTRY:
                cursor += self._restage("post-show", timing=timing)
            elif action in _RESTAGE_AFTER_ACTIONS:
                cursor += self._restage(
                    f"post-{action.lower()}", timing=timing,
                )

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

        # PR M — subject color inheritance for callouts. When the author
        # sets `subject` (not `anchor`) and omits `color`, walk the
        # subject's palette position. Explicit `color` always wins, so
        # we only patch params when both conditions hold.
        if (
            action == "showCalloutBox"
            and params.get("subject")
            and not params.get("color")
        ):
            from manim_renderer.resolvers.subject_color import (
                inherit_subject_color,
            )
            inherited = inherit_subject_color(
                params["subject"], self._id_to_mobject,
            )
            if inherited is not None:
                params = {**params, "color": inherited}

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
        subject = params.get("subject")
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
        elif subject:
            # PR L — solver-driven placement. Resolve the subject's host
            # mobject, pick the best side, and assemble an anchor string
            # so the downstream leader-line code (CalloutBox.position_finalized)
            # behaves identically.
            from manim_renderer.resolvers.subject_placement import (
                pick_subject_side, resolve_subject_target,
            )

            anchor_target = resolve_subject_target(subject, self._id_to_mobject)
            callout_size = None
            if hasattr(component, "width") and hasattr(component, "height"):
                callout_size = (float(component.width), float(component.height))
            layout_direction = "vertical" if fmt == "vertical" else "horizontal"
            side = pick_subject_side(
                anchor_target, fmt,
                callout_size=callout_size,
                layout_direction=layout_direction,
            )
            # Build an anchor string the existing pipeline understands.
            anchor = f"{side}:{subject.split(':', 1)[0]}"
            place_at_anchor(component, anchor_target, anchor, fmt)

        # Defense in depth: validator already rejects duplicate ids. Assert here
        # so a bypass during dev fails loudly rather than silently overwriting.
        if component.id:
            assert component.id not in self._id_to_mobject, (
                f"duplicate id {component.id!r} reached scene runner; "
                f"validator should have caught this"
            )
            self._id_to_mobject[component.id] = component
            # PR F: seed _roles from the component's own resolved role
            # (BaseComponent.__init__ reads params.role with DEFAULT_ROLE as
            # the fallback — annotation for CalloutBox, primary for the rest).
            self._roles[component.id] = component.role
            # PR J: stash solver inputs. `preferred_size(params, fmt, role)`
            # is called on every restage; we keep the original params (without
            # the `_slot_bounds` annotation) so the answer doesn't drift.
            clean_params = {k: v for k, v in params.items()
                            if not k.startswith("_")}
            self._params_by_id[component.id] = clean_params
            self._class_by_id[component.id] = ComponentCls
            self._id_to_slot[component.id] = slot_name

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

    # --- restage (Phase 2 / PR G) -------------------------------------------

    def _cast(self) -> list[CastMember]:
        """Materialize the current cast for the solver.

        For every live id we resolve `(role, slot, preferred_size)`:
          * role from `_roles` (defaults to `primary` for legacy children
            registered via `extra_id_registrations` that the runner never
            seeded).
          * slot from `_id_to_slot` (None for anchored components).
          * preferred_size from the recorded class + params; fall back to
            the mobject's current bbox for children/orphans that never
            went through `_dispatch_component`.
        """
        out: list[CastMember] = []
        for id_, mob in self._id_to_mobject.items():
            role = self._roles.get(id_, "primary")
            slot = self._id_to_slot.get(id_)
            cls = self._class_by_id.get(id_)
            params = self._params_by_id.get(id_)
            if cls is not None and params is not None:
                try:
                    pref = cls.preferred_size(params, self._format, role)
                except Exception:
                    # Defensive: never let a measure failure break restage.
                    pref = (float(getattr(mob, "width", 0.0) or 0.01),
                            float(getattr(mob, "height", 0.0) or 0.01))
            else:
                pref = (float(getattr(mob, "width", 0.0) or 0.01),
                        float(getattr(mob, "height", 0.0) or 0.01))
            out.append(CastMember(
                id=id_, role=role, preferred_size=pref, slot=slot,
            ))
        return out

    def _compute_target_rects(self) -> dict[str, Rect]:
        """Plan the next stage rects for the current cast.

        PR J wires this to `self._layout.solve(cast)`. Members the solver
        skips (anchored callouts pre-PR L) keep their current bbox so the
        identity-delta check in `_restage` leaves them in place.
        """
        cast = self._cast()
        solved = self._layout.solve(cast)

        targets: dict[str, Rect] = {}
        for id_, mob in self._id_to_mobject.items():
            if id_ in solved:
                targets[id_] = solved[id_]
                continue
            # Solver chose not to place this id (anchored / child / hidden).
            # Keep the mobject's current bbox so the restage pass treats
            # it as identity and leaves it alone.
            c = mob.get_center()
            w = max(0.01, float(getattr(mob, "width", 0.0) or 0.0))
            h = max(0.01, float(getattr(mob, "height", 0.0) or 0.0))
            targets[id_] = Rect(
                cx=float(c[0]), cy=float(c[1]), width=w, height=h,
            )
        return targets

    def _restage(self, reason: str = "", *, timing: str = "fast") -> float:
        """FLIP-style restage pass over the live cast.

        Steps:
          1. Capture — record each live mobject's current center + scale.
          2. Plan — call `_compute_target_rects()` for new positions/sizes.
          3. Animate — for each id with a non-zero delta, build a Transform.
             Identity planner (PR G) leaves all deltas zero, so the pass
             returns immediately without calling `self.play`.

        Returns the run_time consumed by the restage animation (0 if no
        movement happened, which is the PR G default).
        """
        if not self._id_to_mobject:
            return 0.0

        # Capture
        state: dict[str, tuple[np.ndarray, float]] = {
            id_: (np.array(mob.get_center(), dtype=float), 1.0)
            for id_, mob in self._id_to_mobject.items()
        }
        self._restage_state = state

        # Plan
        targets = self._compute_target_rects()

        # Animate non-zero deltas. PR G: identity → empty list.
        run_time = TIMING.get(timing, TIMING["fast"])
        anims = []
        for id_, target in targets.items():
            mob = self._id_to_mobject.get(id_)
            if mob is None:
                continue
            current_center, _ = state[id_]
            target_center = target.center
            if np.allclose(current_center, target_center, atol=_RESTAGE_POS_TOL):
                continue
            anims.append(
                mob.animate(run_time=run_time).move_to(target_center)
            )
            # Overlays follow their host with a parallel Transform — PR G
            # never reaches this branch, but the hook is wired so PR I+
            # doesn't have to re-discover it.
            for overlay in self._overlays_by_host.get(id_, []):
                delta = target_center - current_center
                anims.append(
                    overlay.animate(run_time=run_time)
                    .shift(delta)
                )

        if not anims:
            return 0.0

        self.play(AnimationGroup(*anims))
        return float(run_time)

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

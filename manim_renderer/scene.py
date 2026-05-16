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

Restage (+):
  After every composition change (show, removeComponent, setRole) the runner
  calls `_restage(reason)`. The pass captures the live cast's current state,
  asks `_compute_target_rects` for new positions/sizes, and Transforms anything
  that moved. Mutations (highlightCell, crossOut, bestResponseArrow) do NOT
  trigger restage; their overlays follow the host via the parallel walker over
  `_overlays_by_host`. In PR G the planner returns identity, so no movement
  actually happens — this PR just wires the trigger points.
"""

from __future__ import annotations

import os
import sys

import numpy as np
from manim import AnimationGroup, MovingCameraScene, Transform

from manim_renderer.actions import ActionContext
from manim_renderer.layouts.base import CastMember, Rect
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY
from manim_renderer.resolvers.anchor import parse_anchor, place_at_anchor
from manim_renderer.theme.timing import TIMING

# opt-in terminal trace. Set GEOPOAI_DEBUG=1 to print a per-restage
# summary (cast composition + solver plan + animation count) to stderr.
# Costs ~zero when unset (one os.environ check per restage).
_DEBUG = bool(os.environ.get("GEOPOAI_DEBUG"))

# Phase ordering for sort tiebreaks at the same `at`.
_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2

# Actions that change composition and therefore trigger a restage pass.
# Mutations (highlightCell, crossOut, bestResponseArrow) are deliberately
# absent — overlays follow their host via the parallel walker, not a fresh
# layout solve.
_RESTAGE_AFTER_ACTIONS = {"removeComponent", "setRole", "setLayout"}

# How close two positions need to be before we treat a restage delta as
# "didn't move" (skip Transform). Absolute units, matches Manim defaults.
_RESTAGE_POS_TOL = 1e-4
# How close to 1.0 the scale ratio must be before we skip the scale step.
_RESTAGE_SCALE_TOL = 1e-3


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
        # Role tracking (): every show action seeds an entry
        # here; `setRole` mutates it. Drives the restage pass (PR G+).
        self._roles: dict[str, str] = {}
        # per-id solver inputs. Used by `_cast()` to ask each
        # component class for `preferred_size(params, fmt, role)` on every
        # restage. Updated on show; entries dropped on remove.
        self._id_to_slot: dict[str, str | None] = {}
        self._params_by_id: dict[str, dict] = {}
        self._class_by_id: dict[str, type] = {}
        # Last-seen restage state for diagnostics. Map id -> (center, scale).
        self._restage_state: dict[str, tuple[np.ndarray, float]] = {}
        # first-show bbox size per id. Restage computes target scale
        # relative to THIS size, not the live width, so successive role
        # changes don't compound and drift the mobject toward zero.
        self._restage_base_size: dict[str, tuple[float, float]] = {}
        # when a callout uses params.subject, we record the host id
        # here so the solver can split that host's slot rect and reserve a
        # side region for the callout. Absent → static-anchor path used.
        self._subject_host_by_id: dict[str, str] = {}
        # provenance per id: "slots" vs "overlays". Consumed by
        # setLayout to keep slots-block components pinned (hidden on
        # incompatible swaps) rather than auto-migrating to a fallback.
        self._slot_origin_by_id: dict[str, str] = {}

        events = self._collect_events(scene)

        cursor = 0.0
        for slot_name, _phase, ev in events:
            at = float(ev["at"])
            if at > cursor:
                self.wait(at - cursor)
                cursor = at

            action = ev["action"]
            params = ev.get("params") or {}

            timing = params.get("timing", "normal")

            if action in COMPONENT_REGISTRY:
                anim = self._dispatch_component(
                    action, params, slot_name, fmt
                )
                new_id = params.get("id")
                # Universal sequencing: any new component reaches its
                # solver target BEFORE its entrance plays. The existing
                # cast restages first (animating to their new positions);
                # the new component is invisible to the scene until its
                # entrance fires, so it enters directly at its target
                # without drifting. See `_show_at_solver_target`.
                cursor += self._show_at_solver_target(
                    new_id, anim, timing,
                )
            elif action in ACTION_REGISTRY:
                anim = self._dispatch_action(action, params, fmt)
                if anim is not None:
                    self.play(anim)
                    cursor = at + (anim.run_time or 0.0)
                if action in _RESTAGE_AFTER_ACTIONS:
                    cursor += self._restage(
                        f"post-{action.lower()}", timing=timing,
                    )
            else:
                raise ValueError(
                    f"unknown action {action!r}; "
                    f"components: {sorted(COMPONENT_REGISTRY)}, "
                    f"actions: {sorted(ACTION_REGISTRY)}"
                )

        if duration > cursor:
            self.wait(duration - cursor)

    # --- dispatch ------------------------------------------------------------

    @staticmethod
    def _anchor_host_id_from(anchor: str | None) -> str | None:
        """Parse the host id out of an anchor string (`right-of:pd` → `pd`).
        Returns None if the input isn't a valid anchor string."""
        if not isinstance(anchor, str):
            return None
        try:
            _, host_id = parse_anchor(anchor)
        except ValueError:
            return None
        return host_id

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

        # overlay events arrive with slot_name=None. If the event
        # also lacks anchor/subject, the solver would never place it and the
        # mobject would render at scene origin. Auto-bind to the layout's
        # primary content slot, or use the author-specified `params.slot`.
        if slot_name is None:
            explicit_slot = params.get("slot")
            if (
                explicit_slot is None
                and not params.get("anchor")
                and not params.get("subject")
            ):
                from manim_renderer.layouts.base import PRIMARY_SLOT
                explicit_slot = PRIMARY_SLOT.get(self._layout.name)
            if (
                explicit_slot is not None
                and self._layout.has_slot(explicit_slot)
            ):
                slot_name = explicit_slot

        # Slot-bounds hint: when a component is placed in a slot, expose the
        # slot's (width, height) so text-bearing components can auto-fit. Pass
        # via params with a leading-underscore key to mark it as internal
        # (validator runs before this; it never sees `_slot_bounds`).
        slot_rect = self._layout.slot(slot_name) if slot_name is not None else None
        if slot_rect is not None:
            params = {**params, "_slot_bounds": (slot_rect.width, slot_rect.height)}

        # subject color inheritance for callouts. When the
        # author omits `color`, walk the subject (or anchor target) and use
        # the host's palette key. Explicit `params.color` always wins.
        if (
            action == "showCalloutBox"
            and not params.get("color")
        ):
            from manim_renderer.resolvers.subject_color import (
                inherit_subject_color,
            )
            inheritance_target = params.get("subject") or self._anchor_host_id_from(
                params.get("anchor"),
            )
            if inheritance_target:
                inherited = inherit_subject_color(
                    inheritance_target, self._id_to_mobject,
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
            # solver-driven placement. Resolve the subject's
            # host, do an initial `place_at_anchor` so the callout has a
            # valid pre-restage position, AND record the host id in
            # `_subject_host_by_id` so the next restage pass treats the
            # callout as a slot member that reserves a side region in
            # the host's slot. The restage Transform then slides it into
            # the solver-chosen final position.
            from manim_renderer.resolvers.subject_placement import (
                parse_subject, pick_subject_side, resolve_subject_target,
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
            host_id, _refinement = parse_subject(subject)
            # Build an anchor string the existing pipeline understands.
            anchor = f"{side}:{host_id}"
            place_at_anchor(component, anchor_target, anchor, fmt)

        # Defense in depth: validator already rejects duplicate ids. Assert here
        # so a bypass during dev fails loudly rather than silently overwriting.
        if component.id:
            assert component.id not in self._id_to_mobject, (
                f"duplicate id {component.id!r} reached scene runner; "
                f"validator should have caught this"
            )
            self._id_to_mobject[component.id] = component
            # seed _roles from the component's own resolved role
            # (BaseComponent.__init__ reads params.role with DEFAULT_ROLE as
            # the fallback — annotation for CalloutBox, primary for the rest).
            self._roles[component.id] = component.role
            # stash solver inputs. `preferred_size(params, fmt, role)`
            # is called on every restage; we keep the original params (without
            # the `_slot_bounds` annotation) so the answer doesn't drift.
            clean_params = {k: v for k, v in params.items()
                            if not k.startswith("_")}
            self._params_by_id[component.id] = clean_params
            self._class_by_id[component.id] = ComponentCls
            self._id_to_slot[component.id] = slot_name
            # slots-block events arrive with a non-None slot_name;
            # overlay/timeline events arrive with slot_name=None. The
            # distinction lets setLayout keep slots-block components pinned.
            # Tolerate test fixtures that bypass construct().
            if hasattr(self, "_slot_origin_by_id"):
                self._slot_origin_by_id[component.id] = (
                    "slots" if slot_name is not None else "overlays"
                )

            # Callouts inherit subject-pack semantics from their host
            # whenever a subject/anchor is present — even when the author
            # also specified an explicit `slot`. Without this, a callout
            # written as `{slot:"body", subject:"bars"}` would be treated
            # as a peer of bars (both flexed inside body) and drift on
            # restage instead of packing as host+callout pair.
            if action == "showCalloutBox":
                callout_host_id: str | None = None
                if subject:
                    from manim_renderer.resolvers.subject_placement import (
                        parse_subject as _ps,
                    )
                    callout_host_id, _ = _ps(subject)
                elif anchor:
                    callout_host_id = self._anchor_host_id_from(anchor)
                if callout_host_id is not None:
                    host_slot = self._id_to_slot.get(callout_host_id)
                    if host_slot is not None:
                        # Inherit only when the author didn't pick one
                        # explicitly. An author-set slot wins so multi-slot
                        # custom placements stay honored, but the subject
                        # host link is recorded either way so the solver
                        # packs them when they share a slot.
                        if not slot_name:
                            self._id_to_slot[component.id] = host_slot
                        self._subject_host_by_id[component.id] = callout_host_id

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

        # capture the build-time bbox so restage scales against a
        # stable reference, not the live (already-scaled) width. Without
        # this anchor, successive role changes compound multiplicatively
        # and components drift toward zero. Test fixtures that bypass
        # construct() may not seed `_restage_base_size`; tolerate that.
        if component.id and hasattr(self, "_restage_base_size"):
            self._restage_base_size[component.id] = (
                float(getattr(component, "width", 0.0) or 0.01),
                float(getattr(component, "height", 0.0) or 0.01),
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

    # --- restage () -------------------------------------------

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
        subject_map = getattr(self, "_subject_host_by_id", {}) or {}
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
            # anchor-mode callouts carry their explicit side in
            # `params.anchor` so the solver pack respects it.
            anchor_side = None
            if id_ in subject_map and params is not None:
                anchor_str = params.get("anchor")
                if isinstance(anchor_str, str):
                    try:
                        anchor_side, _ = parse_anchor(anchor_str)
                    except ValueError:
                        anchor_side = None
            out.append(CastMember(
                id=id_, role=role, preferred_size=pref, slot=slot,
                subject_host_id=subject_map.get(id_),
                anchor_side=anchor_side,
            ))
        return out

    def _compute_target_rects(self) -> dict[str, Rect]:
        """Plan the next stage rects for the current cast.

        wires this to `self._layout.solve(cast)`. Members the solver
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

    def _show_at_solver_target(
        self,
        new_id: str | None,
        entrance: "Animation | None",
        timing: str,
    ) -> float:
        """Sequence a new component's debut so it appears at its solver
        target rect directly — no drift from the dispatch position to
        the layout-determined final position.

        Steps:
          1. Compute the solver plan with the new component already in
             the cast (the dispatcher registered it).
          2. Move the new component to its target rect's center
             (no animation). Position-only sentinel rects still use
             their `center` so this works uniformly.
          3. Restage the EXISTING cast: their stored positions vs new
             targets produce real animations; the new component is at
             its target now so the identity check skips it (and it
             isn't in the scene render list yet anyway — the entrance
             introducer adds it next).
          4. Play the component's entrance animation. It runs at the
             final position.

        The result: existing cast moves first, then the new component
        appears at its destination via its native entrance (FadeIn,
        count-up, level-by-level, …). No mobject ever drifts from
        slot/anchor to solver target.
        """
        if not new_id or new_id not in self._id_to_mobject:
            consumed = 0.0
            if entrance is not None:
                self.play(entrance)
                consumed += float(entrance.run_time or 0.0)
            consumed += self._restage("post-show", timing=timing)
            return consumed

        new_mob = self._id_to_mobject[new_id]
        targets = self._compute_target_rects()
        target = targets.get(new_id)
        if target is not None:
            # Pre-apply both scale AND position so the restage identity
            # check skips this mobject — otherwise restage would queue
            # a scale animation, add the mobject to scene via the
            # AnimationGroup, and the user sees the callout shrink into
            # place before the entrance fires.
            if target.width > 0 and target.height > 0:
                base_w, base_h = self._restage_base_size.get(
                    new_id,
                    (float(getattr(new_mob, "width", 0.0) or 0.01),
                     float(getattr(new_mob, "height", 0.0) or 0.01)),
                )
                target_scale = min(
                    target.width / max(1e-4, base_w),
                    target.height / max(1e-4, base_h),
                    1.0,
                )
                if abs(target_scale - 1.0) > _RESTAGE_SCALE_TOL:
                    new_mob.scale(target_scale)
            new_mob.move_to(target.center)

        consumed = self._restage("post-show", timing=timing)

        if entrance is not None:
            self.play(entrance)
            consumed += float(entrance.run_time or 0.0)
        return consumed

    def _restage(self, reason: str = "", *, timing: str = "fast") -> float:
        """FLIP-style restage pass over the live cast.

        Steps:
          1. Capture — record each live mobject's current center.
          2. Plan — call `_compute_target_rects()` for new positions/sizes.
          3. Animate — for each id with a non-zero center delta or scale
             delta, build a chained `scale(...).move_to(...)` animation.
             Identity targets produce no animation.

        Scale is computed from `_restage_base_size` (the build-time bbox)
        so successive role changes don't compound. Overlays follow the
        host's transform in parallel.
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

        run_time = TIMING.get(timing, TIMING["fast"])
        anims = []
        for id_, target in targets.items():
            mob = self._id_to_mobject.get(id_)
            if mob is None:
                continue
            current_center, _ = state[id_]
            target_center = target.center

            # Position-only sentinel: when Layout.solve returns a Rect
            # with zero dimensions, the solver is signalling "center this
            # mobject at target.cx/cy and DO NOT scale it". Used for lone
            # primary/hero passthrough so a tall TextCard doesn't get
            # shrunk to fit a short slot.
            position_only = target.width <= 0.0 or target.height <= 0.0

            if position_only:
                position_changed = not np.allclose(
                    current_center, target_center, atol=_RESTAGE_POS_TOL,
                )
                if not position_changed:
                    continue
                anims.append(
                    mob.animate(run_time=run_time).move_to(target_center)
                )
                relative_scale = 1.0
                scale_changed = False
            else:
                # Scale relative to the build-time bbox (not live width) so
                # successive restages don't compound. Missing base size
                # (child of MetricGroup, test fixture bypassing dispatcher)
                # falls back to the mobject's current bbox — identity scale.
                base_size_map = getattr(self, "_restage_base_size", {}) or {}
                base_w, base_h = base_size_map.get(
                    id_,
                    (float(getattr(mob, "width", 0.0) or 0.01),
                     float(getattr(mob, "height", 0.0) or 0.01)),
                )
                cur_w = max(1e-4, float(getattr(mob, "width", 0.0) or 0.0))
                cur_h = max(1e-4, float(getattr(mob, "height", 0.0) or 0.0))
                target_scale_w = target.width / max(1e-4, base_w)
                target_scale_h = target.height / max(1e-4, base_h)
                # Never scale a mobject larger than its build-time size.
                # Slot rects can exceed the natural bbox; growing distorts.
                target_scale = min(target_scale_w, target_scale_h, 1.0)
                current_scale = max(cur_w / base_w, cur_h / base_h)
                # Manim's `.animate.scale(k)` is relative to current size,
                # not absolute, so divide by current scale to get the
                # delta factor.
                relative_scale = target_scale / max(1e-4, current_scale)

                position_changed = not np.allclose(
                    current_center, target_center, atol=_RESTAGE_POS_TOL,
                )
                scale_changed = (
                    abs(relative_scale - 1.0) > _RESTAGE_SCALE_TOL
                )

                if not position_changed and not scale_changed:
                    continue

                animator = mob.animate(run_time=run_time)
                if scale_changed:
                    animator = animator.scale(relative_scale)
                if position_changed:
                    animator = animator.move_to(target_center)
                anims.append(animator)

            # Overlays travel with their host. Two paths:
            #   1. Recipe-based: the mutation action attached a rebuild
            #      callable; we feed it a synthetic host positioned at
            #      target state and Transform the overlay smoothly to
            #      the new geometry. Used for arrows (whose tips don't
            #      scale linearly) and any geometry tied to host anchors.
            #   2. Legacy scale+shift: the overlay is animated directly
            #      using scale around the host's old center then a shift
            #      so the math matches the host transform. Used for
            #      overlays without a recipe.
            if position_only:
                delta = target_center - current_center
                for overlay in self._overlays_by_host.get(id_, []):
                    recipe = getattr(overlay, "_rebuild_recipe", None)
                    if recipe is not None:
                        # Position-only host — synthetic host has the same
                        # geometry (no scale) just moved to the new center.
                        synthetic = mob.copy().shift(delta)
                        try:
                            new_overlay = recipe(synthetic)
                            anims.append(Transform(
                                overlay, new_overlay, run_time=run_time,
                            ))
                            continue
                        except Exception:
                            pass
                    if abs(delta[0]) + abs(delta[1]) > _RESTAGE_POS_TOL:
                        anims.append(
                            overlay.animate(run_time=run_time).shift(delta)
                        )
            else:
                delta = target_center - current_center
                for overlay in self._overlays_by_host.get(id_, []):
                    recipe = getattr(overlay, "_rebuild_recipe", None)
                    if recipe is not None:
                        # Build a positioned + scaled copy of the host to
                        # serve as the synthetic target. Manim's mob.copy()
                        # snapshots the current state; we apply the same
                        # scale + move_to as the real host's animation.
                        synthetic = mob.copy()
                        if scale_changed:
                            synthetic.scale(
                                relative_scale,
                                about_point=current_center,
                            )
                        synthetic.move_to(target_center)
                        try:
                            new_overlay = recipe(synthetic)
                            anims.append(Transform(
                                overlay, new_overlay, run_time=run_time,
                            ))
                            continue
                        except Exception:
                            # Defensive: a misbehaving recipe shouldn't
                            # break restage. Fall through to scale+shift.
                            pass
                    # Legacy walker — scale around host's current center
                    # (not the overlay's), then shift. This produces the
                    # mathematically correct transform: P_new =
                    # host_target + scale * (P_old - host_old).
                    ov_anim = overlay.animate(run_time=run_time)
                    if scale_changed:
                        ov_anim = ov_anim.scale(
                            relative_scale, about_point=current_center,
                        )
                    if position_changed:
                        ov_anim = ov_anim.shift(delta)
                    anims.append(ov_anim)

        if _DEBUG:
            self._debug_trace(reason, targets, len(anims), run_time)

        if not anims:
            self._reposition_subject_callouts()
            return 0.0

        self.play(AnimationGroup(*anims))
        # after the Transform completes, re-anchor each subject
        # callout's leader to the host's new edge. Without this, the
        # leader stays at build-time geometry and visually detaches.
        self._reposition_subject_callouts()
        return float(run_time)

    def _debug_trace(
        self,
        reason: str,
        targets: dict[str, Rect],
        num_anims: int,
        run_time: float,
    ) -> None:
        """Print a multi-line restage summary to stderr. Gated by
        GEOPOAI_DEBUG. Writes nothing to the rendered MP4."""
        cast = self._cast()
        renderer_time = getattr(self, "renderer", None)
        # Manim doesn't expose a public cursor; we approximate via the
        # restage_state snapshot timestamp. For simplicity emit "?" — the
        # `reason` already encodes which event triggered this restage.
        lines = [
            f"[restage] reason={reason!r} layout={self._layout.name!r}"
            f" cast={len(cast)} plan={len(targets)} anims={num_anims}"
            f" run_time={run_time:.2f}s",
        ]
        for m in cast:
            subject = m.subject_host_id or "-"
            lines.append(
                f"    {m.id:<22} role={m.role:<10} slot={str(m.slot):<8}"
                f" subject={subject}"
            )
        for id_, rect in targets.items():
            cur_mob = self._id_to_mobject.get(id_)
            cur_w = float(getattr(cur_mob, "width", 0.0) or 0.0) if cur_mob else 0.0
            cur_h = float(getattr(cur_mob, "height", 0.0) or 0.0) if cur_mob else 0.0
            lines.append(
                f"    plan {id_:<18} target=({rect.cx:+6.2f}, {rect.cy:+6.2f})"
                f" size=({rect.width:5.2f}x{rect.height:5.2f})"
                f" cur=({cur_w:5.2f}x{cur_h:5.2f})"
            )
        # Prepend \n so the block lands on its own line even when Manim's
        # \r-based progress bars share stderr. Saved logs can still be
        # filtered cleanly with `tr '\r' '\n' < log | grep '^\[restage\]'`.
        sys.stderr.write("\n" + "\n".join(lines) + "\n")
        sys.stderr.flush()

    def _reposition_subject_callouts(self) -> None:
        """Tell every subject-bound callout to rebuild its leader line
        from the host's current edge. Called at the end of `_restage`."""
        subject_map = getattr(self, "_subject_host_by_id", {}) or {}
        if not subject_map:
            return
        for callout_id, host_id in subject_map.items():
            callout = self._id_to_mobject.get(callout_id)
            host = self._id_to_mobject.get(host_id)
            if callout is None or host is None:
                continue
            reposition = getattr(callout, "reposition", None)
            if callable(reposition):
                reposition(host_mob=host, format=self._format)

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

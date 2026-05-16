"""Spatial overflow checks for the validator (tiers 4a, 4c, 4b).

Three pure-function checks that run BEFORE any Manim mobject is constructed.
Each component contributes a `measure(params, format) -> (width, height)`
estimate (see `BaseComponent.measure`); these checks consume those estimates
plus the layout's slot rects and the format's frame bounds.

Tier 4a — slot fit (`check_slot_fits`)
  For each event placed in a named slot, check the component's measured bbox
  fits within the slot's (width, height).

Tier 4c — anchored overflow (`check_anchor_overflows`)
  For each anchored event, compute where the resulting component will land
  (using a simulated `place_at_anchor`) and check the resulting bbox stays
  within `FRAME_BOUNDS[format]`.

Tier 4b — collision dry-run (`check_collisions`)
  Walk all events in (at, phase) order. Maintain a live dict of placed
  bboxes. For each `show*` event compute the new bbox; check (a) it fits
  the frame and (b) it does not overlap any currently-live component. For
  each `removeComponent` event, drop the target from the live set. Mutation
  actions don't trigger collision checks (overlays don't count as cast).

All three return list[str] of error strings (empty = passed). Cost is
dominated by `measure()` calls — pure Python, no Manim. Sub-millisecond
per event.
"""

from __future__ import annotations

from dataclasses import dataclass

from manim_renderer.layouts.base import FRAME_BOUNDS
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY
from manim_renderer.resolvers.anchor import (
    ANCHOR_TOKENS,
    DEFAULT_ANCHOR_BUFF,
    parse_anchor,
)
from manim_renderer.resolvers.subject_placement import parse_subject

# Phase ordering mirrors `scene.py` and `validator.py`.
_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2

# In vertical format, lateral anchors auto-flip — mirrors `resolve_anchor`.
_VERTICAL_FLIP = {"right-of": "below", "left-of": "above"}

# Components whose measure() can be safely skipped when the run-time scene is
# expected to keep them inside the slot (none today, but a hook for future).
_MEASURE_SKIP: set[str] = set()


# --- internal bbox dataclass -------------------------------------------------


@dataclass(frozen=True)
class _Bbox:
    """Axis-aligned bbox in Manim units: center + half-extents."""
    cx: float
    cy: float
    half_w: float
    half_h: float

    @property
    def left(self) -> float:
        return self.cx - self.half_w

    @property
    def right(self) -> float:
        return self.cx + self.half_w

    @property
    def bottom(self) -> float:
        return self.cy - self.half_h

    @property
    def top(self) -> float:
        return self.cy + self.half_h

    def fits_frame(self, frame_w: float, frame_h: float) -> bool:
        half_fw = frame_w / 2
        half_fh = frame_h / 2
        return (
            self.left   >= -half_fw - _FRAME_TOL
            and self.right  <=  half_fw + _FRAME_TOL
            and self.bottom >= -half_fh - _FRAME_TOL
            and self.top    <=  half_fh + _FRAME_TOL
        )

    def overlaps(self, other: "_Bbox") -> bool:
        if self.right <= other.left + _OVERLAP_TOL: return False
        if self.left  >= other.right - _OVERLAP_TOL: return False
        if self.top   <= other.bottom + _OVERLAP_TOL: return False
        if self.bottom >= other.top   - _OVERLAP_TOL: return False
        return True


# Allow a small tolerance so estimator rounding doesn't trigger spurious errors.
# Tuned so the typical PD scene neither over- nor under-flags.
_FRAME_TOL = 0.10
_OVERLAP_TOL = 0.05


def _measure_component(action: str, params: dict, format: str) -> tuple[float, float]:
    """Look up a component's `measure(params, format)` class method.

    Returns (0.0, 0.0) for actions that aren't components (mutations) — the
    callers all guard on action membership first; this is defense in depth.
    """
    cls = COMPONENT_REGISTRY.get(action)
    if cls is None:
        return (0.0, 0.0)
    return cls.measure(params, format)


def _bbox_at(center: tuple[float, float], size: tuple[float, float]) -> _Bbox:
    cx, cy = center
    w, h = size
    return _Bbox(cx=cx, cy=cy, half_w=w / 2, half_h=h / 2)


def _anchored_center(
    token: str,
    target_bbox: _Bbox,
    size: tuple[float, float],
    buff: float = DEFAULT_ANCHOR_BUFF,
) -> tuple[float, float]:
    """Simulate `place_at_anchor` — return where the new component's center
    lands when next_to'd against `target_bbox`. Mirrors the geometry in
    `resolvers/anchor.py:place_at_anchor`."""
    w, h = size
    if token == "above":
        return (target_bbox.cx, target_bbox.top + buff + h / 2)
    if token == "below":
        return (target_bbox.cx, target_bbox.bottom - buff - h / 2)
    if token == "right-of":
        return (target_bbox.right + buff + w / 2, target_bbox.cy)
    if token == "left-of":
        return (target_bbox.left - buff - w / 2, target_bbox.cy)
    if token == "inside":
        return (target_bbox.cx, target_bbox.cy)
    raise ValueError(f"unknown anchor token {token!r}")


def _pick_subject_side_bbox(
    host: _Bbox,
    callout_size: tuple[float, float],
    fmt: str,
    layout_direction: str,
    buff: float = DEFAULT_ANCHOR_BUFF,
) -> str:
    """Pure-bbox port of `resolvers.subject_placement.pick_subject_side`.

    Walks the same preference order, returns the first side whose callout
    fits inside FRAME_BOUNDS, falls back to the last candidate even if it
    overflows. Used by the validator dry-run to predict where the runtime
    solver will land a subject-based callout.
    """
    frame_w, frame_h = FRAME_BOUNDS.get(fmt, FRAME_BOUNDS["horizontal"])
    cw, ch = callout_size

    # Round 3 — match `subject_placement.pick_subject_side`: horizontal
    # layouts only consider horizontal sides, vertical only vertical.
    if layout_direction == "vertical":
        order = ("below", "above")
    else:
        order = ("right-of", "left-of")

    def fits(side: str) -> bool:
        if side == "right-of":
            return host.right + buff + cw <= frame_w / 2.0
        if side == "left-of":
            return host.left - buff - cw >= -frame_w / 2.0
        if side == "above":
            return host.top + buff + ch <= frame_h / 2.0
        if side == "below":
            return host.bottom - buff - ch >= -frame_h / 2.0
        return False

    for side in order:
        if fits(side):
            return side
    return order[-1]


def _iter_events(scene: dict):
    """Yield (json_path, event, slot_name_or_None, phase). Mirrors
    `validator._iter_events` exactly."""
    for slot_name, ev in (scene.get("slots") or {}).items():
        yield f"slots.{slot_name}", ev, slot_name, _PHASE_SLOT
    for i, ev in enumerate(scene.get("overlays") or []):
        yield f"overlays[{i}]", ev, None, _PHASE_OVERLAY
    for i, ev in enumerate(scene.get("timeline") or []):
        yield f"timeline[{i}]", ev, None, _PHASE_TIMELINE


# --- tier 4a: slot fit -------------------------------------------------------


def check_slot_fits(scene: dict) -> list[str]:
    """For each slot-placed component, check measure() ≤ slot bounds.

    Skips actions not in `COMPONENT_REGISTRY` (slot events are always
    components by schema, but defense in depth).
    """
    errors: list[str] = []
    fmt = scene.get("format")
    layout_name = (scene.get("scene") or {}).get("layout")
    if not fmt or not layout_name:
        return errors

    try:
        layout = resolve_layout(layout_name, fmt)
    except ValueError:
        return errors  # validator's earlier tier reported this

    for slot_name, ev in (scene.get("slots") or {}).items():
        action = ev.get("action")
        if action not in COMPONENT_REGISTRY:
            continue
        if action in _MEASURE_SKIP:
            continue
        if not layout.has_slot(slot_name):
            continue  # validator's earlier tier reported this
        params = ev.get("params") or {}
        try:
            w, h = _measure_component(action, params, fmt)
        except Exception as e:
            errors.append(
                f"[layout-fit] slots.{slot_name}: measure() raised on "
                f"{action}: {e}"
            )
            continue
        slot = layout.slot(slot_name)
        if w > slot.width + _FRAME_TOL or h > slot.height + _FRAME_TOL:
            errors.append(
                f"[layout-fit] slots.{slot_name}: {action} measures "
                f"({w:.2f}, {h:.2f}) but slot {slot_name!r} of layout "
                f"{layout_name!r} holds ({slot.width:.2f}, {slot.height:.2f}); "
                f"try size:small or a different layout"
            )
    return errors


# --- tier 4c: anchored overflow ---------------------------------------------


def check_anchor_overflows(scene: dict) -> list[str]:
    """For each anchored event, simulate placement and check the resulting
    bbox stays within FRAME_BOUNDS[format]."""
    errors: list[str] = []
    fmt = scene.get("format")
    if not fmt or fmt not in FRAME_BOUNDS:
        return errors
    frame_w, frame_h = FRAME_BOUNDS[fmt]

    layout_name = (scene.get("scene") or {}).get("layout")
    if not layout_name:
        return errors
    try:
        layout = resolve_layout(layout_name, fmt)
    except ValueError:
        return errors

    # Pre-compute slot bboxes for any id that gets placed via a slot.
    slot_bboxes_by_id: dict[str, _Bbox] = {}
    for slot_name, ev in (scene.get("slots") or {}).items():
        action = ev.get("action")
        if action not in COMPONENT_REGISTRY or not layout.has_slot(slot_name):
            continue
        params = ev.get("params") or {}
        ident = params.get("id")
        if not ident:
            continue
        try:
            size = _measure_component(action, params, fmt)
        except Exception:
            continue
        slot = layout.slot(slot_name)
        slot_bboxes_by_id[ident] = _bbox_at((slot.cx, slot.cy), size)

    # Walk events in sort order; for each anchored event, compute landing bbox.
    sorted_events = sorted(
        _iter_events(scene),
        key=lambda t: (float(t[1].get("at", 0.0)), t[3]),
    )
    live: dict[str, _Bbox] = dict(slot_bboxes_by_id)

    for ev_path, ev, slot_name, _phase in sorted_events:
        if not isinstance(ev, dict):
            continue
        action = ev.get("action")
        params = ev.get("params") or {}
        if action in ACTION_REGISTRY:
            # Mutation actions don't move the cast spatially.
            if action == "removeComponent":
                target = params.get("target")
                if isinstance(target, str):
                    live.pop(target, None)
            continue
        if action not in COMPONENT_REGISTRY:
            continue

        anchor = params.get("anchor")
        subject = params.get("subject")
        ident = params.get("id")

        if slot_name is not None:
            # Slot-placed → already in `live`; nothing to check here.
            continue

        bbox: _Bbox | None = None
        if isinstance(anchor, str):
            try:
                token, ref_id = parse_anchor(anchor)
            except ValueError:
                continue
            if fmt == "vertical":
                token = _VERTICAL_FLIP.get(token, token)
            if token not in ANCHOR_TOKENS:
                continue
            target_bbox = live.get(ref_id)
            if target_bbox is None:
                continue
            try:
                size = _measure_component(action, params, fmt)
            except Exception as e:
                errors.append(
                    f"[anchor-overflow] {ev_path}: measure() raised on "
                    f"{action}: {e}"
                )
                continue
            center = _anchored_center(token, target_bbox, size)
            bbox = _bbox_at(center, size)
            if not bbox.fits_frame(frame_w, frame_h):
                errors.append(
                    f"[anchor-pollutes-frame] {ev_path}: {action} anchored "
                    f"{anchor!r} lands at ({bbox.cx:.2f}, {bbox.cy:.2f}) with "
                    f"extents ({bbox.half_w * 2:.2f} × {bbox.half_h * 2:.2f}); "
                    f"exceeds frame bounds ({frame_w:.2f} × {frame_h:.2f})"
                )
        elif isinstance(subject, str):
            # Subject-based callouts: predict the side `pick_subject_side`
            # will return and check the resulting bbox.
            try:
                host_id, _refinement = parse_subject(subject)
            except ValueError:
                continue
            target_bbox = live.get(host_id)
            if target_bbox is None:
                continue
            try:
                size = _measure_component(action, params, fmt)
            except Exception as e:
                errors.append(
                    f"[anchor-overflow] {ev_path}: measure() raised on "
                    f"{action}: {e}"
                )
                continue
            layout_direction = (
                "vertical" if fmt == "vertical" else "horizontal"
            )
            side = _pick_subject_side_bbox(
                target_bbox, size, fmt, layout_direction,
            )
            if fmt == "vertical":
                side = _VERTICAL_FLIP.get(side, side)
            center = _anchored_center(side, target_bbox, size)
            bbox = _bbox_at(center, size)
            if not bbox.fits_frame(frame_w, frame_h):
                errors.append(
                    f"[anchor-pollutes-frame] {ev_path}: {action} subject "
                    f"{subject!r} (predicted side {side!r}) lands at "
                    f"({bbox.cx:.2f}, {bbox.cy:.2f}) with extents "
                    f"({bbox.half_w * 2:.2f} × {bbox.half_h * 2:.2f}); "
                    f"exceeds frame bounds ({frame_w:.2f} × {frame_h:.2f})"
                )
        else:
            continue

        if bbox is not None and ident:
            live[ident] = bbox
    return errors


# --- tier 4b: collision dry-run ---------------------------------------------


def check_collisions(scene: dict) -> list[str]:
    """Full dry-run walk maintaining a live cast. For each show*, check frame
    fit + pairwise non-intersection with live cast. For each removeComponent,
    drop from live. Mutation overlays are not tracked here (they're cleaned
    by the host removal; collision against the host is what matters)."""
    errors: list[str] = []
    fmt = scene.get("format")
    if not fmt or fmt not in FRAME_BOUNDS:
        return errors
    frame_w, frame_h = FRAME_BOUNDS[fmt]

    layout_name = (scene.get("scene") or {}).get("layout")
    if not layout_name:
        return errors
    try:
        layout = resolve_layout(layout_name, fmt)
    except ValueError:
        return errors

    sorted_events = sorted(
        _iter_events(scene),
        key=lambda t: (float(t[1].get("at", 0.0)), t[3]),
    )
    live: dict[str, _Bbox] = {}

    for ev_path, ev, slot_name, _phase in sorted_events:
        if not isinstance(ev, dict):
            continue
        action = ev.get("action")
        params = ev.get("params") or {}

        if action == "removeComponent":
            target = params.get("target")
            if isinstance(target, str):
                live.pop(target, None)
            continue
        if action in ACTION_REGISTRY:
            continue
        if action not in COMPONENT_REGISTRY:
            continue

        ident = params.get("id")
        try:
            size = _measure_component(action, params, fmt)
        except Exception as e:
            errors.append(
                f"[collision-overlap] {ev_path}: measure() raised on "
                f"{action}: {e}"
            )
            continue

        # Determine bbox: slot-placed vs anchored vs subject.
        bbox: _Bbox | None = None
        if slot_name is not None and layout.has_slot(slot_name):
            slot = layout.slot(slot_name)
            bbox = _bbox_at((slot.cx, slot.cy), size)
        else:
            anchor = params.get("anchor")
            subject = params.get("subject")
            if isinstance(anchor, str):
                try:
                    token, ref_id = parse_anchor(anchor)
                except ValueError:
                    continue
                if fmt == "vertical":
                    token = _VERTICAL_FLIP.get(token, token)
                target_bbox = live.get(ref_id)
                if target_bbox is None:
                    continue
                center = _anchored_center(token, target_bbox, size)
                bbox = _bbox_at(center, size)
            elif isinstance(subject, str):
                try:
                    host_id, _refinement = parse_subject(subject)
                except ValueError:
                    continue
                target_bbox = live.get(host_id)
                if target_bbox is None:
                    continue
                layout_direction = (
                    "vertical" if fmt == "vertical" else "horizontal"
                )
                side = _pick_subject_side_bbox(
                    target_bbox, size, fmt, layout_direction,
                )
                if fmt == "vertical":
                    side = _VERTICAL_FLIP.get(side, side)
                center = _anchored_center(side, target_bbox, size)
                bbox = _bbox_at(center, size)
        if bbox is None:
            continue

        # Frame fit.
        if not bbox.fits_frame(frame_w, frame_h):
            errors.append(
                f"[frame-overflow] {ev_path}: {action} bbox center "
                f"({bbox.cx:.2f}, {bbox.cy:.2f}) extents "
                f"({size[0]:.2f} × {size[1]:.2f}) exceeds frame "
                f"({frame_w:.2f} × {frame_h:.2f})"
            )

        # Pairwise overlap. Skip `inside:` anchors — those are overlays by intent.
        anchor = params.get("anchor")
        is_inside = (
            isinstance(anchor, str) and anchor.startswith("inside:")
        )
        if not is_inside:
            for other_id, other_bbox in live.items():
                if bbox.overlaps(other_bbox):
                    errors.append(
                        f"[collision-overlap] {ev_path} at t={ev.get('at', 0)}: "
                        f"{action} bbox overlaps {other_id!r}"
                    )

        if ident:
            live[ident] = bbox
    return errors


# --- tier 4d: composition fit via the layout solver (PR N) ----------------


# Annotated cast member — extends `layouts.base.CastMember` with extra fields
# the composition checker needs (original params, action name) without
# leaking them into the public Layout.solve signature.
from manim_renderer.layouts.base import CastMember as _CastMember


@dataclass(frozen=True)
class _AnnotatedCastMember(_CastMember):
    params: dict = None  # type: ignore[assignment]
    action: str = ""


def check_composition_fit(scene: dict) -> list[str]:
    """Walk events in order, maintain the cast, and ask `layout.solve(cast)`
    for planned rects at each step. Flag two failure modes:

      * `[composition-fit]` — solver allocates a rect that exceeds frame
        bounds (the cast simply can't fit in this layout).
      * `[composition-overlap]` — solver returns overlapping rects (this
        shouldn't happen with the default solver, but a custom solver
        could produce it).

    Mutation actions are skipped; setRole updates the cast's role for the
    current id without spawning a new entry.
    """
    from manim_renderer.layouts.base import CastMember

    errors: list[str] = []
    fmt = scene.get("format")
    if not fmt or fmt not in FRAME_BOUNDS:
        return errors
    frame_w, frame_h = FRAME_BOUNDS[fmt]

    layout_name = (scene.get("scene") or {}).get("layout")
    if not layout_name:
        return errors
    try:
        layout = resolve_layout(layout_name, fmt)
    except ValueError:
        return errors

    sorted_events = sorted(
        _iter_events(scene),
        key=lambda t: (float(t[1].get("at", 0.0)), t[3]),
    )

    cast_by_id: dict[str, CastMember] = {}
    current_layout = layout
    current_layout_name = layout_name
    event_idx = 0

    for ev_path, ev, slot_name, _phase in sorted_events:
        event_idx += 1
        if not isinstance(ev, dict):
            continue
        action = ev.get("action")
        params = ev.get("params") or {}

        # Maintain the cast.
        if action == "removeComponent":
            target = params.get("target")
            if isinstance(target, str):
                cast_by_id.pop(target, None)
            continue
        if action == "setLayout":
            new_name = params.get("layout")
            if not isinstance(new_name, str):
                continue
            try:
                current_layout = resolve_layout(new_name, fmt)
                current_layout_name = new_name
            except ValueError as e:
                errors.append(
                    f"[layout-incompatible-format] {ev_path}: {e}"
                )
            continue
        if action == "setRole":
            target = params.get("target")
            new_role = params.get("role")
            if target in cast_by_id and isinstance(new_role, str):
                old = cast_by_id[target]
                cls = COMPONENT_REGISTRY.get(_class_action_for(old))
                if cls is not None and hasattr(cls, "preferred_size"):
                    try:
                        pref = cls.preferred_size(old.params, fmt, new_role)
                    except Exception:
                        pref = old.preferred_size
                else:
                    pref = old.preferred_size
                cast_by_id[target] = _AnnotatedCastMember(
                    id=old.id, role=new_role, preferred_size=pref,
                    slot=old.slot, params=old.params, action=old.action,
                )
            continue
        if action in ACTION_REGISTRY:
            # Mutations leave composition unchanged.
            continue
        if action not in COMPONENT_REGISTRY:
            continue

        ident = params.get("id")
        if not ident:
            continue

        role = params.get(
            "role",
            "annotation" if action == "showCalloutBox" else "primary",
        )
        cls = COMPONENT_REGISTRY[action]
        try:
            if hasattr(cls, "preferred_size"):
                pref = cls.preferred_size(params, fmt, role)
            else:
                pref = cls.measure(params, fmt)
        except Exception:
            continue

        # PR W: subject callouts join the host's slot so the solver
        # carves a side region for them and shrinks the host.
        effective_slot = slot_name
        subject_host = None
        if (action == "showCalloutBox" and params.get("subject")
                and not slot_name):
            try:
                host_id, _ = parse_subject(params["subject"])
            except ValueError:
                host_id = None
            if host_id and host_id in cast_by_id:
                effective_slot = cast_by_id[host_id].slot
                subject_host = host_id

        cast_by_id[ident] = _AnnotatedCastMember(
            id=ident, role=role, preferred_size=pref,
            slot=effective_slot, subject_host_id=subject_host,
            params=params, action=action,
        )

        # Ask the solver for planned rects with the cast so far.
        cast = list(cast_by_id.values())
        try:
            plan = current_layout.solve(cast)
        except Exception as e:
            errors.append(
                f"[composition-fit] {ev_path}: layout "
                f"{current_layout_name!r}.solve raised: {e}"
            )
            continue

        # Frame fit.
        for rid, rect in plan.items():
            half_w = rect.width / 2
            half_h = rect.height / 2
            fits = (
                rect.cx - half_w >= -frame_w / 2 - _FRAME_TOL
                and rect.cx + half_w <=  frame_w / 2 + _FRAME_TOL
                and rect.cy - half_h >= -frame_h / 2 - _FRAME_TOL
                and rect.cy + half_h <=  frame_h / 2 + _FRAME_TOL
            )
            if not fits:
                primary_count = sum(
                    1 for m in cast if m.role == "primary"
                )
                errors.append(
                    f"[composition-fit] {ev_path}: {action} with "
                    f"{primary_count} primaries in "
                    f"{current_layout_name!r} overflows frame at {rid!r}; "
                    f"suggest a wider layout (e.g. 'trio') or sequence "
                    f"the entrances."
                )

        # Pairwise overlap among planned rects.
        ids = list(plan.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = plan[ids[i]]
                b = plan[ids[j]]
                if _rects_overlap(a, b):
                    # PR W: tag subject-host overlaps with a dedicated
                    # error string so authors get actionable feedback.
                    mi = cast_by_id.get(ids[i])
                    mj = cast_by_id.get(ids[j])
                    subject_overlap = (
                        (mi and getattr(mi, "subject_host_id", None) == ids[j])
                        or (mj and getattr(mj, "subject_host_id", None) == ids[i])
                    )
                    if subject_overlap:
                        errors.append(
                            f"[subject-overlaps-host] {ev_path}: solver carve "
                            f"left subject callout overlapping its host in "
                            f"{current_layout_name!r} (ids {ids[i]!r} ↔ "
                            f"{ids[j]!r}). Try a smaller callout width, a "
                            f"less crowded slot, or move the host to a "
                            f"roomier layout."
                        )
                    else:
                        errors.append(
                            f"[composition-overlap] {ev_path}: solver assigned "
                            f"overlapping rects to {ids[i]!r} and {ids[j]!r} "
                            f"in {current_layout_name!r}."
                        )

    return errors


def _rects_overlap(a, b) -> bool:
    """Two Rects overlap if their axis projections both intersect."""
    if a.cx + a.width / 2 <= b.cx - b.width / 2 + _OVERLAP_TOL: return False
    if a.cx - a.width / 2 >= b.cx + b.width / 2 - _OVERLAP_TOL: return False
    if a.cy + a.height / 2 <= b.cy - b.height / 2 + _OVERLAP_TOL: return False
    if a.cy - a.height / 2 >= b.cy + b.height / 2 - _OVERLAP_TOL: return False
    return True


def _class_action_for(member) -> str | None:
    """Resolve the action name a recorded CastMember came from."""
    return getattr(member, "action", None)


# --- combined entry ----------------------------------------------------------


def run_overflow_checks(scene: dict) -> list[str]:
    """Run 4a, 4c, 4b, 4d in order. Always called from `validator.validate()`."""
    errors: list[str] = []
    errors.extend(check_slot_fits(scene))
    errors.extend(check_anchor_overflows(scene))
    errors.extend(check_collisions(scene))
    errors.extend(check_composition_fit(scene))
    return errors

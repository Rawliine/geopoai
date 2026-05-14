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
        if not isinstance(anchor, str) or slot_name is not None:
            # Slot-placed → already in `live`; nothing to check here.
            continue
        try:
            token, ref_id = parse_anchor(anchor)
        except ValueError:
            continue  # validator's tier 4 will surface this
        if fmt == "vertical":
            token = _VERTICAL_FLIP.get(token, token)
        if token not in ANCHOR_TOKENS:
            continue

        target_bbox = live.get(ref_id)
        if target_bbox is None:
            continue  # validator's tier 4 will surface this
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
                f"[anchor-overflow] {ev_path}: {action} anchored {anchor!r} "
                f"lands at ({bbox.cx:.2f}, {bbox.cy:.2f}) with extents "
                f"({bbox.half_w * 2:.2f} × {bbox.half_h * 2:.2f}); exceeds "
                f"frame bounds ({frame_w:.2f} × {frame_h:.2f})"
            )
        # Register this bbox so later anchors can chain off it.
        ident = params.get("id")
        if ident:
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

        # Determine bbox: slot-placed vs anchored.
        bbox: _Bbox | None = None
        if slot_name is not None and layout.has_slot(slot_name):
            slot = layout.slot(slot_name)
            bbox = _bbox_at((slot.cx, slot.cy), size)
        else:
            anchor = params.get("anchor")
            if isinstance(anchor, str):
                try:
                    token, ref_id = parse_anchor(anchor)
                except ValueError:
                    continue
                if fmt == "vertical":
                    token = _VERTICAL_FLIP.get(token, token)
                target_bbox = live.get(ref_id)
                if target_bbox is None:
                    continue  # validator's tier 4 will surface
                center = _anchored_center(token, target_bbox, size)
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


# --- combined entry ----------------------------------------------------------


def run_overflow_checks(scene: dict) -> list[str]:
    """Run 4a, 4c, 4b in order. Always called from `validator.validate()`."""
    errors: list[str] = []
    errors.extend(check_slot_fits(scene))
    errors.extend(check_anchor_overflows(scene))
    errors.extend(check_collisions(scene))
    return errors

"""Manim-free scene replay.

Walks a scene JSON in event order, maintains the cast (slot bindings,
roles, subject relationships), calls `Layout.solve(cast)` after every
composition-changing event, and prints the solver plan to stdout. Mirrors
the trace `GEOPOAI_DEBUG=1` writes from a real render, but runs in a
fraction of a second — useful for diagnosing solver behavior without
spinning up Manim.

Usage:
    python scripts/manim/debug_replay.py scripts/manim/qa_roles.json

Compatible with every action the schema accepts; unknown actions are
reported as `unknown` and skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from manim_renderer.layouts.base import PRIMARY_SLOT, CastMember, Rect
from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import ACTION_REGISTRY, COMPONENT_REGISTRY
from manim_renderer.resolvers.anchor import parse_anchor
from manim_renderer.resolvers.subject_placement import parse_subject


_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2


def _iter_events(scene: dict):
    for slot_name, ev in (scene.get("slots") or {}).items():
        yield slot_name, _PHASE_SLOT, ev
    for ev in scene.get("overlays") or []:
        yield None, _PHASE_OVERLAY, ev
    for ev in scene.get("timeline") or []:
        yield None, _PHASE_TIMELINE, ev


def _preferred(cls, params: dict, fmt: str, role: str) -> tuple[float, float]:
    try:
        if hasattr(cls, "preferred_size"):
            return cls.preferred_size(params, fmt, role)
        return cls.measure(params, fmt)
    except Exception:
        return (1.0, 1.0)


def _fmt_rect(rect: Rect) -> str:
    return (
        f"({rect.cx:+6.2f}, {rect.cy:+6.2f}) "
        f"size=({rect.width:5.2f}x{rect.height:5.2f})"
    )


def _print_header(t: float, ev_index: int, action: str, ident: str, reason: str):
    print()
    print(
        f"== t={t:6.2f}s  #{ev_index:>3}  {action:<22}  id={ident:<18}"
        f" reason={reason}"
    )


def _print_cast(cast: list[CastMember]):
    print(f"  cast ({len(cast)}):")
    for m in cast:
        subj = m.subject_host_id or "-"
        print(
            f"    {m.id:<22} role={m.role:<10} slot={str(m.slot):<8}"
            f" pref=({m.preferred_size[0]:5.2f}x{m.preferred_size[1]:5.2f})"
            f" subject={subj}"
        )


def _print_plan(plan: dict[str, Rect]):
    print(f"  plan ({len(plan)}):")
    for id_, rect in plan.items():
        print(f"    {id_:<22} {_fmt_rect(rect)}")


def replay(scene: dict) -> None:
    fmt = scene.get("format", "horizontal")
    layout_name = (scene.get("scene") or {}).get("layout", "hero")
    layout = resolve_layout(layout_name, fmt)
    print(f"# scene: format={fmt} initial_layout={layout_name}")

    sorted_events = sorted(
        _iter_events(scene),
        key=lambda t: (float(t[2].get("at", 0.0)), t[1]),
    )

    cast_by_id: dict[str, CastMember] = {}
    subject_host_by_id: dict[str, str] = {}
    slot_origin_by_id: dict[str, str] = {}

    for idx, (slot_name, _phase, ev) in enumerate(sorted_events):
        if not isinstance(ev, dict):
            continue
        action = ev.get("action", "")
        params = ev.get("params") or {}
        at = float(ev.get("at", 0.0))
        ident = params.get("id") or params.get("target") or "-"

        if action in COMPONENT_REGISTRY:
            role = params.get(
                "role",
                "annotation" if action == "showCalloutBox" else "primary",
            )
            cls = COMPONENT_REGISTRY[action]
            pref = _preferred(cls, params, fmt, role)
            effective_slot = slot_name
            subject_host = None
            anchor_side = None
            subject = params.get("subject")
            anchor = params.get("anchor")

            # Mirror scene.py Round 3 auto-bind: overlay events with no
            # explicit slot/anchor/subject fall back to the layout's
            # primary slot.
            if effective_slot is None:
                explicit = params.get("slot")
                if explicit is None and not anchor and not subject:
                    explicit = PRIMARY_SLOT.get(layout.name)
                if explicit and explicit in layout.slots:
                    effective_slot = explicit

            # Subject-mode callouts join the host's slot.
            if action == "showCalloutBox" and subject and not effective_slot:
                try:
                    host_id, _ = parse_subject(subject)
                except ValueError:
                    host_id = None
                if host_id and host_id in cast_by_id:
                    effective_slot = cast_by_id[host_id].slot
                    subject_host = host_id

            # Round 3 — anchor-mode callouts also join the host's slot
            # and remember the explicit side so the pack honors it.
            if (action == "showCalloutBox" and anchor
                    and not subject and not effective_slot):
                try:
                    side, host_id = parse_anchor(anchor)
                except ValueError:
                    side, host_id = None, None
                if host_id and host_id in cast_by_id:
                    effective_slot = cast_by_id[host_id].slot
                    subject_host = host_id
                    anchor_side = side
            cm = CastMember(
                id=params.get("id", ident),
                role=role,
                preferred_size=pref,
                slot=effective_slot,
                subject_host_id=subject_host,
                anchor_side=anchor_side,
            )
            cast_by_id[cm.id] = cm
            slot_origin_by_id[cm.id] = (
                "slots" if slot_name is not None else "overlays"
            )
            if subject_host:
                subject_host_by_id[cm.id] = subject_host
            _print_header(at, idx, action, cm.id, "show")
            _print_cast(list(cast_by_id.values()))
            _print_plan(layout.solve(list(cast_by_id.values())))

        elif action == "removeComponent":
            target = params.get("target")
            if isinstance(target, str):
                cast_by_id.pop(target, None)
                subject_host_by_id.pop(target, None)
                slot_origin_by_id.pop(target, None)
            _print_header(at, idx, action, str(target), "remove")
            _print_plan(layout.solve(list(cast_by_id.values())))

        elif action == "setRole":
            target = params.get("target")
            new_role = params.get("role")
            if target in cast_by_id and isinstance(new_role, str):
                old = cast_by_id[target]
                cls = COMPONENT_REGISTRY.get(_class_from_action_history(old))
                pref = (
                    _preferred(cls, params, fmt, new_role) if cls
                    else old.preferred_size
                )
                cast_by_id[target] = CastMember(
                    id=old.id, role=new_role, preferred_size=pref,
                    slot=old.slot, subject_host_id=old.subject_host_id,
                )
            _print_header(at, idx, action, str(target), f"role={new_role}")
            _print_plan(layout.solve(list(cast_by_id.values())))

        elif action == "setLayout":
            new_name = params.get("layout", "")
            try:
                layout = resolve_layout(new_name, fmt)
            except ValueError as e:
                print(f"  !! setLayout failed: {e}")
                continue
            # Mirror set_layout.py: pin slots-block ids, migrate overlays.
            for cid, cm in list(cast_by_id.items()):
                if cm.slot is None:
                    continue
                if cm.slot in layout.slots:
                    continue
                if slot_origin_by_id.get(cid) == "slots":
                    cast_by_id[cid] = CastMember(
                        id=cm.id, role="hidden",
                        preferred_size=cm.preferred_size,
                        slot=None, subject_host_id=cm.subject_host_id,
                    )
                else:
                    fallback = (
                        sorted(layout.slots)[0] if layout.slots else None
                    )
                    cast_by_id[cid] = CastMember(
                        id=cm.id, role=cm.role,
                        preferred_size=cm.preferred_size,
                        slot=fallback, subject_host_id=cm.subject_host_id,
                    )
            _print_header(at, idx, action, "-", f"layout={new_name}")
            _print_plan(layout.solve(list(cast_by_id.values())))

        elif action in ACTION_REGISTRY:
            _print_header(at, idx, action, str(ident), "mutation")
        else:
            _print_header(at, idx, action or "?", str(ident), "unknown")


# We don't carry per-cast-member action history in CastMember; for the
# replay we approximate by looking up the original event in the scene.
# This helper returns the action string for a recorded id (or None).
_action_by_id: dict[str, str] = {}


def _class_from_action_history(member: CastMember) -> str | None:
    return _action_by_id.get(member.id)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: python scripts/manim/debug_replay.py <scene.json>",
            file=sys.stderr,
        )
        return 2
    path = Path(argv[1])
    scene = json.loads(path.read_text())
    # Seed the action-history map by walking events once.
    for _slot, _phase, ev in _iter_events(scene):
        if not isinstance(ev, dict):
            continue
        ident = (ev.get("params") or {}).get("id")
        if ident and ev.get("action") in COMPONENT_REGISTRY:
            _action_by_id[ident] = ev["action"]
    replay(scene)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

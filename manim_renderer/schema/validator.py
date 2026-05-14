"""Four-tier scene validator: structural, action-level, semantic, anchor.

Tiers:
  1. Structural   — jsonschema against scene_schema.json
  1b. Coords-banned — AGENT.md rule 1: x/y/position/coords keys forbidden anywhere
  2. Action-level — jsonschema against schema/action_schemas/<snake_action>.json,
                    with $ref resolution into scene_schema.json's definitions block
  3. Semantic     — layout/slot resolution, format/layout compatibility, at <= duration,
                    unique ids
  4. Anchors      — every `params.anchor` (or `params.target` for actions) references
                    an id declared by a strictly-earlier event in (at, phase) order
                    matching the scene runner's traversal
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import jsonschema
import referencing
import referencing.jsonschema

from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.resolvers.anchor import parse_anchor

_SCHEMA_DIR = Path(__file__).parent
_ACTION_DIR = _SCHEMA_DIR / "action_schemas"

_BANNED_COORD_KEYS = {"x", "y", "position", "coords", "coordinate", "coordinates"}

# Format/layout compatibility — single source of truth used by both validator
# and tests. Add new layouts here AND in layouts/{horizontal,vertical}.py.
LAYOUT_FORMATS: dict[str, set[str]] = {
    "hero":       {"horizontal", "vertical"},
    "split":      {"horizontal"},
    "stacked":    {"vertical"},
    "data-left":  {"horizontal"},
    "data-top":   {"vertical"},
    "trio":       {"horizontal"},
    "trio-stack": {"vertical"},
    "title-body": {"horizontal", "vertical"},
}

# Match the scene runner's _PHASE_* constants exactly.
_PHASE_SLOT = 0
_PHASE_OVERLAY = 1
_PHASE_TIMELINE = 2

# Param keys that hold an anchor string (as opposed to a bare id).
_ANCHOR_PARAM_KEYS = ("anchor",)
# Param keys that hold a bare id reference to an existing component.
_ID_REF_PARAM_KEYS = ("target",)


# --- per-action id extractors ------------------------------------------------
#
# Some components register additional child ids at runtime via
# `BaseComponent.extra_id_registrations`. The validator needs to see these to
# (a) include them in the duplicate-id check, and (b) treat them as valid
# anchor targets. Each entry maps action name -> callable(params) -> list[id].
# Entries here MUST stay in sync with the matching component's
# `extra_id_registrations` implementation.

def _ids_from_metric_group(params: dict) -> list[str]:
    return [s["id"] for s in params.get("stats", []) if isinstance(s, dict) and s.get("id")]


def _ids_from_timeline(params: dict) -> list[str]:
    return [e["id"] for e in params.get("events", []) if isinstance(e, dict) and e.get("id")]


def _ids_from_alliance_web(params: dict) -> list[str]:
    return [n["id"] for n in params.get("nodes", []) if isinstance(n, dict) and n.get("id")]


_ACTION_ID_EXTRACTORS: dict[str, callable] = {
    "showMetricGroup":  _ids_from_metric_group,
    "showTimeline":     _ids_from_timeline,
    "showAllianceWeb":  _ids_from_alliance_web,
}

# Phase 1.5: highlightCell / crossOut / bestResponseArrow accept an optional
# `id` exposing the overlay as a top-level addressable id. They DO NOT need
# an extractor — `_ids_declared_by` picks up `params.id` automatically via
# the `own = params.get("id")` path. Adding an extractor here would double-
# count the id and trigger a spurious `[semantic-id] duplicate id` error.


def _ids_declared_by(action: str, params: dict) -> list[str]:
    """Return the full list of ids an event declares: its own id (if any) plus
    any nested child ids from a registered extractor."""
    out: list[str] = []
    own = params.get("id")
    if own:
        out.append(own)
    extractor = _ACTION_ID_EXTRACTORS.get(action)
    if extractor:
        out.extend(extractor(params))
    return out


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _scene_schema() -> dict:
    return _load(_SCHEMA_DIR / "scene_schema.json")


def _camel_to_snake(name: str) -> str:
    return "".join(("_" + c.lower()) if c.isupper() else c for c in name).lstrip("_")


def _action_schema(action: str) -> dict | None:
    path = _ACTION_DIR / f"{_camel_to_snake(action)}.json"
    if not path.exists():
        return None
    return _load(path)


def _make_registry() -> referencing.Registry:
    """Registry that resolves ../scene_schema.json refs from action schemas."""
    scene = referencing.Resource.from_contents(_scene_schema())
    # Action schemas use "../scene_schema.json#/definitions/..." — register
    # under that exact relative URI plus the bare filename for both styles.
    return referencing.Registry().with_resources([
        ("../scene_schema.json", scene),
        ("scene_schema.json", scene),
    ])


def _iter_events(scene: dict) -> Iterable[tuple[str, dict, str | None, int]]:
    """Yields (json_path, event, slot_name_or_None, phase)."""
    for slot_name, ev in (scene.get("slots") or {}).items():
        yield f"slots.{slot_name}", ev, slot_name, _PHASE_SLOT
    for i, ev in enumerate(scene.get("overlays") or []):
        yield f"overlays[{i}]", ev, None, _PHASE_OVERLAY
    for i, ev in enumerate(scene.get("timeline") or []):
        yield f"timeline[{i}]", ev, None, _PHASE_TIMELINE


def _walk(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def validate(scene: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []

    # Tier 1a: structural
    try:
        jsonschema.validate(scene, _scene_schema())
    except jsonschema.ValidationError as e:
        errors.append(
            f"[structural] {'/'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}"
        )

    # Tier 1b: AGENT.md rule 1 — coordinates banned anywhere in JSON
    for path, key, _v in _walk(scene):
        if key in _BANNED_COORD_KEYS:
            errors.append(
                f"[coords-banned] {path}: key {key!r} not allowed; "
                "use slots or anchors (e.g. 'below:id')"
            )

    # Tier 2: per-action params (with $ref resolution into scene_schema.json)
    registry = _make_registry()
    for ev_path, ev, _slot, _phase in _iter_events(scene):
        if not isinstance(ev, dict):
            continue
        action = ev.get("action")
        if not action:
            continue
        a_schema = _action_schema(action)
        if a_schema is None:
            errors.append(f"[action-unknown] {ev_path}.action: {action!r} has no schema")
            continue
        try:
            jsonschema.Draft7Validator(a_schema, registry=registry).validate(
                ev.get("params") or {}
            )
        except jsonschema.ValidationError as e:
            relpath = "/".join(str(p) for p in e.absolute_path) or ""
            errors.append(f"[action-params] {ev_path}.params/{relpath}: {e.message}")

    # Tier 3: semantic
    fmt = scene.get("format")
    scene_block = scene.get("scene") if isinstance(scene.get("scene"), dict) else {}
    duration = float(scene_block.get("duration", 0.0))
    layout_name = scene_block.get("layout")

    layout = None
    if fmt and layout_name:
        try:
            layout = resolve_layout(layout_name, fmt)
        except ValueError as e:
            errors.append(f"[layout-unknown] scene.layout: {e}")

        # Format/layout compatibility check (separate from "layout exists")
        compat = LAYOUT_FORMATS.get(layout_name)
        if compat is not None and fmt not in compat:
            errors.append(
                f"[layout-format] scene.layout={layout_name!r} does not support "
                f"format={fmt!r}; supported: {sorted(compat)}"
            )

    if layout is not None:
        for slot_name in (scene.get("slots") or {}).keys():
            if not layout.has_slot(slot_name):
                errors.append(
                    f"[layout-slot] slots.{slot_name}: layout {layout_name!r} "
                    f"({fmt}) has no slot {slot_name!r}; "
                    f"available: {sorted(layout.slots)}"
                )

    seen_ids: set[str] = set()
    for ev_path, ev, _slot, _phase in _iter_events(scene):
        if not isinstance(ev, dict):
            continue
        at = float(ev.get("at", 0.0))
        if duration and at > duration:
            errors.append(
                f"[semantic-at] {ev_path}.at={at} exceeds scene.duration={duration}"
            )
        params = ev.get("params") or {}
        action = ev.get("action")
        for ident in _ids_declared_by(action, params):
            if ident in seen_ids:
                errors.append(f"[semantic-id] duplicate id {ident!r} at {ev_path}")
            seen_ids.add(ident)

    # Tier 4: anchors
    errors.extend(_validate_anchors(scene))

    # Tier 5: spatial dry-run (4a slot-fit + 4c anchor-overflow + 4b collisions).
    # Always on; cost is pure-math (no Manim mobjects). See `_dry_run.py`.
    # Only run if earlier tiers haven't already failed with structural errors —
    # malformed scenes can break the dry-run walk in confusing ways.
    if not errors:
        from manim_renderer.schema._dry_run import run_overflow_checks
        errors.extend(run_overflow_checks(scene))

    return (len(errors) == 0, errors)


def _validate_anchors(scene: dict) -> list[str]:
    """Every anchor target (or id-ref param) must reference an id declared by an
    earlier event under the runner's (at, phase) ordering."""
    errors: list[str] = []
    sorted_events = sorted(
        _iter_events(scene),
        key=lambda t: (float(t[1].get("at", 0.0)), t[3]),
    )

    declared: set[str] = set()
    for ev_path, ev, _slot, _phase in sorted_events:
        if not isinstance(ev, dict):
            continue
        params = ev.get("params") or {}

        # Check anchor-shaped refs
        for key in _ANCHOR_PARAM_KEYS:
            anchor = params.get(key)
            if not isinstance(anchor, str):
                continue
            try:
                _token, ref_id = parse_anchor(anchor)
            except ValueError as e:
                errors.append(f"[anchor-shape] {ev_path}.params.{key}: {e}")
                continue
            if ref_id not in declared:
                errors.append(
                    f"[anchor-target] {ev_path}.params.{key}={anchor!r}: "
                    f"id {ref_id!r} not declared by any earlier event "
                    f"(known so far: {sorted(declared)})"
                )

        # Check bare id-ref params (target on actions like removeComponent)
        for key in _ID_REF_PARAM_KEYS:
            ref_id = params.get(key)
            if not isinstance(ref_id, str):
                continue
            if ref_id not in declared:
                errors.append(
                    f"[id-ref] {ev_path}.params.{key}={ref_id!r}: id not declared "
                    f"by any earlier event (known so far: {sorted(declared)})"
                )

        # Declare this event's id(s) AFTER checking refs — so an event cannot
        # anchor against itself OR against ids it declares (e.g. a callout
        # in the same MetricGroup event can't target a stat declared in the
        # same params block).
        action = ev.get("action")
        for ident in _ids_declared_by(action, params):
            declared.add(ident)

    return errors


def _cli():
    if len(sys.argv) < 2:
        print("usage: python -m manim_renderer.schema.validator <scene.json>")
        sys.exit(2)
    scene = _load(Path(sys.argv[1]))
    ok, errs = validate(scene)
    if ok:
        print("OK")
        sys.exit(0)
    for e in errs:
        print(e)
    sys.exit(1)


if __name__ == "__main__":
    _cli()

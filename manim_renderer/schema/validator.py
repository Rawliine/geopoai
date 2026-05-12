"""Three-tier scene validator: structural, action-level, semantic.

Tiers (recap §15):
  1. Structural   — jsonschema against scene_schema.json
  2. Action-level — jsonschema against schema/action_schemas/<snake_action>.json
  3. Semantic    — layout/slot resolution, at <= duration, unique ids,
                    coordinate-key ban (AGENT.md rule 1)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import jsonschema

from manim_renderer.layouts.resolver import available_layouts, resolve_layout

_SCHEMA_DIR = Path(__file__).parent
_ACTION_DIR = _SCHEMA_DIR / "action_schemas"

_BANNED_COORD_KEYS = {"x", "y", "position", "coords", "coordinate", "coordinates"}


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


def _iter_events(scene: dict) -> Iterable[tuple[str, dict, str | None]]:
    """Yields (json_path, event, slot_name_or_None)."""
    for slot_name, ev in (scene.get("slots") or {}).items():
        yield f"slots.{slot_name}", ev, slot_name
    for i, ev in enumerate(scene.get("overlays") or []):
        yield f"overlays[{i}]", ev, None
    for i, ev in enumerate(scene.get("timeline") or []):
        yield f"timeline[{i}]", ev, None


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

    # Tier 2: per-action params
    for ev_path, ev, _slot in _iter_events(scene):
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
            jsonschema.validate(ev.get("params") or {}, a_schema)
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

    if layout is not None:
        for slot_name in (scene.get("slots") or {}).keys():
            if not layout.has_slot(slot_name):
                errors.append(
                    f"[layout-slot] slots.{slot_name}: layout {layout_name!r} "
                    f"({fmt}) has no slot {slot_name!r}; "
                    f"available: {sorted(layout.slots)}"
                )

    seen_ids: set[str] = set()
    for ev_path, ev, _slot in _iter_events(scene):
        if not isinstance(ev, dict):
            continue
        at = float(ev.get("at", 0.0))
        if duration and at > duration:
            errors.append(
                f"[semantic-at] {ev_path}.at={at} exceeds scene.duration={duration}"
            )
        params = ev.get("params") or {}
        ident = params.get("id")
        if ident:
            if ident in seen_ids:
                errors.append(f"[semantic-id] duplicate id {ident!r} at {ev_path}")
            seen_ids.add(ident)

    return (len(errors) == 0, errors)


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

"""Three-tier scene validator: structural, action-level, semantic."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import jsonschema

_SCHEMA_DIR = Path(__file__).parent
_ACTION_DIR = _SCHEMA_DIR / "action_schemas"

_BANNED_COORD_KEYS = {"x", "y", "position", "center"}


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _scene_schema() -> dict:
    return _load(_SCHEMA_DIR / "scene_schema.json")


def _action_schema(action: str) -> dict | None:
    # action names are camelCase; schema files are snake_case
    snake = "".join(("_" + c.lower()) if c.isupper() else c for c in action).lstrip("_")
    path = _ACTION_DIR / f"{snake}.json"
    if not path.exists():
        return None
    return _load(path)


def _iter_events(scene: dict) -> Iterable[tuple[str, dict]]:
    for slot_name, ev in (scene.get("slots") or {}).items():
        yield f"slots.{slot_name}", ev
    for i, ev in enumerate(scene.get("overlays") or []):
        yield f"overlays[{i}]", ev
    for i, ev in enumerate(scene.get("timeline") or []):
        yield f"timeline[{i}]", ev


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

    # Tier 1: structural
    try:
        jsonschema.validate(scene, _scene_schema())
    except jsonschema.ValidationError as e:
        errors.append(
            f"[structural] {'/'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}"
        )

    # Tier 1b: coordinate ban (AGENT.md rule 1)
    for path, key, _v in _walk(scene):
        if key in _BANNED_COORD_KEYS:
            errors.append(
                f"[coords-banned] {path}: key '{key}' not allowed; use zones or anchors"
            )

    # Tier 2: per-action params
    for ev_path, ev in _iter_events(scene):
        if not isinstance(ev, dict):
            continue
        action = ev.get("action")
        if not action:
            continue
        a_schema = _action_schema(action)
        if a_schema is None:
            errors.append(f"[action-unknown] {ev_path}.action: '{action}' has no schema")
            continue
        try:
            jsonschema.validate(ev.get("params") or {}, a_schema)
        except jsonschema.ValidationError as e:
            errors.append(
                f"[action-params] {ev_path}.params/"
                f"{'/'.join(str(p) for p in e.absolute_path) or ''}: {e.message}"
            )

    # Tier 3: semantic
    duration = float(scene.get("scene", {}).get("duration", 0.0)) if scene.get("scene") else 0.0
    seen_ids: set[str] = set()
    for ev_path, ev in _iter_events(scene):
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
                errors.append(f"[semantic-id] duplicate id '{ident}' at {ev_path}")
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

"""scenes (BRAIN) — author per-clip scene JSONs into scenes/.

The artifact is { scenes: { clip_id: <scene dict> } }; merge writes each to the
storyboard entry's `scene_ref`. Validated structurally per renderer (full
per-renderer schema validation happens again at render time).
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestration.context import StageContext
from orchestration.stages import Stage

SCHEMA = {
    "type": "object",
    "required": ["scenes"],
    "additionalProperties": False,
    "properties": {
        "scenes": {"type": "object", "additionalProperties": {"type": "object"}},
    },
}

# Renderers whose scene file is a timed scene (duration required).
_TIMED = {"map", "manim", "escape_hatch"}


def _entries(ctx: StageContext) -> list[dict]:
    return ctx.manifest.get("storyboard", {}).get("entries", [])


def build(ctx: StageContext) -> tuple[str, dict]:
    entries = _entries(ctx)
    needed = [e for e in entries if e.get("scene_ref")]
    instruction = (
        "Author the per-clip scene files as scenes.json — "
        "{ scenes: { <clip_id>: <scene> } } for every storyboard entry that has "
        "a `scene_ref`:\n"
        "- map → a mapbox scene JSON (renderer 'mapbox'); manim → a manim scene; "
        "broll → a shot spec.\n"
        "- On-screen text is compression only — never transcribe the VO.\n"
        "- Each timed scene (map/manim) needs a positive `duration`.\n\n"
        f"Storyboard entries needing scenes:\n{json.dumps(needed, indent=2)}\n\n"
        f"Script beats (for reference):\n"
        f"{json.dumps(ctx.manifest.get('script', {}).get('beats', []), indent=2)}"
    )
    return instruction, SCHEMA


def check(ctx: StageContext, artifact: dict) -> list[str]:
    scenes = artifact.get("scenes", {})
    errors: list[str] = []
    by_clip = {e["clip_id"]: e for e in _entries(ctx)}
    for entry in _entries(ctx):
        ref = entry.get("scene_ref")
        if not ref:
            continue
        clip_id = entry["clip_id"]
        scene = scenes.get(clip_id)
        if scene is None:
            errors.append(f"no scene authored for clip {clip_id!r} (scene_ref {ref})")
            continue
        if not isinstance(scene, dict):
            errors.append(f"scene for {clip_id!r} is not an object")
            continue
        if entry["renderer"] in _TIMED:
            dur = scene.get("duration")
            if not isinstance(dur, (int, float)) or dur <= 0:
                errors.append(f"scene for {clip_id!r} needs a positive duration")
    for clip_id in scenes:
        if clip_id not in by_clip:
            errors.append(f"scene authored for unknown clip {clip_id!r}")
    return errors


def merge(ctx: StageContext, artifact: dict) -> None:
    scenes = artifact.get("scenes", {})
    for entry in _entries(ctx):
        ref = entry.get("scene_ref")
        clip_id = entry["clip_id"]
        if not ref or clip_id not in scenes:
            continue
        out = ctx.ep_dir / ref
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scenes[clip_id], indent=2) + "\n", encoding="utf-8")


STAGE = Stage(name="scenes", is_brain=True, build=build, merge=merge, check=check)

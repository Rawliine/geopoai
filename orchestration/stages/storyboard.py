"""storyboard (BRAIN) — beats → clips (renderer, duration, scene path, media).

Media placement: each media_pool item is placed by its `use` —
broll → a broll clip; manim_media → a manim showMedia; map_mask → maskImage;
map_region → reserveRegion + a post-composition overlay; hook → the opening clip.
Validator: durations ~ script reading time; renderer valid; max consecutive
same-renderer; every media_pool item referenced exactly once.
"""

from __future__ import annotations

import json
import re

from orchestration.context import StageContext
from orchestration.stages import Stage

SCHEMA = {
    "type": "object",
    "required": ["entries"],
    "additionalProperties": False,
    "properties": {
        "entries": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["beat_id", "clip_id", "renderer", "duration"],
                "additionalProperties": False,
                "properties": {
                    "beat_id": {"type": "string", "minLength": 1},
                    "clip_id": {"type": "string", "minLength": 1},
                    "renderer": {
                        "type": "string",
                        "enum": ["map", "manim", "broll", "escape_hatch"],
                    },
                    "duration": {"type": "number", "exclusiveMinimum": 0},
                    "scene_ref": {"type": "string"},
                    "captions": {"type": "boolean"},
                    "format_targets": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["horizontal", "vertical"]},
                    },
                    "media_ref": {"type": "string"},
                },
            },
        }
    },
}


def build(ctx: StageContext) -> tuple[str, dict]:
    bible = ctx.bible
    beats = ctx.manifest.get("script", {}).get("beats", [])
    media = ctx.manifest.get("media_pool", [])
    instruction = (
        "Map beats to clips and author storyboard.json — `entries[]`, each "
        "{ beat_id, clip_id, renderer, duration, scene_ref, captions?, "
        "format_targets?, media_ref? }:\n"
        "- renderer ∈ map | manim | broll | escape_hatch.\n"
        "- scene_ref: the scene-file path to author next (under scenes/).\n"
        "- Place each media_pool item exactly once via `media_ref` (its id); "
        "route by its `use`: broll→broll clip, manim_media→manim, "
        "map_mask→map maskImage, map_region→map reserveRegion + overlay, "
        "hook→opening clip.\n"
        f"- Durations should sum near the script reading time; avoid more than "
        f"{bible.get('thresholds', {}).get('max_consecutive_same_renderer', 3)} "
        "consecutive clips on the same renderer.\n\n"
        f"Component palette:\n{json.dumps(bible.get('component_palette', {}), indent=2)}\n\n"
        f"Beats:\n{json.dumps(beats, indent=2)}\n\n"
        f"Media pool:\n{json.dumps(media, indent=2)}"
    )
    return instruction, SCHEMA


def _script_seconds(ctx: StageContext) -> float:
    wps = ctx.bible.get("thresholds", {}).get("reading_words_per_s", 2.6) or 2.6
    words = 0
    for beat in ctx.manifest.get("script", {}).get("beats", []):
        words += len(re.findall(r"\b\w+\b", beat.get("vo_text", "")))
    return words / wps if words else 0.0


def check(ctx: StageContext, artifact: dict) -> list[str]:
    th = ctx.bible.get("thresholds", {})
    errors: list[str] = []
    entries = artifact.get("entries", [])

    # durations ~ script reading time
    total = sum(float(e["duration"]) for e in entries)
    target = _script_seconds(ctx)
    tol = th.get("duration_tolerance_ratio", 0.2)
    if target and (total < target * (1 - tol) or total > target * (1 + tol)):
        errors.append(
            f"storyboard duration {total:.0f}s is outside ±{tol:.0%} of the "
            f"script reading time {target:.0f}s"
        )

    # max consecutive same-renderer
    cap = th.get("max_consecutive_same_renderer", 3)
    run = 0
    prev = None
    for e in entries:
        run = run + 1 if e["renderer"] == prev else 1
        prev = e["renderer"]
        if run > cap:
            errors.append(
                f"more than {cap} consecutive {e['renderer']!r} clips "
                f"(at clip {e['clip_id']!r})"
            )
            break

    # every media_pool item referenced exactly once
    refs = [e["media_ref"] for e in entries if e.get("media_ref")]
    pool_ids = [m["id"] for m in ctx.manifest.get("media_pool", [])]
    for mid in pool_ids:
        n = refs.count(mid)
        if n != 1:
            errors.append(f"media_pool item {mid!r} referenced {n} times (expected 1)")
    for ref in refs:
        if ref not in pool_ids:
            errors.append(f"storyboard media_ref {ref!r} is not in media_pool")

    # clip ids unique
    ids = [e["clip_id"] for e in entries]
    if len(ids) != len(set(ids)):
        errors.append("duplicate clip_id in storyboard")
    return errors


def merge(ctx: StageContext, artifact: dict) -> None:
    ctx.manifest["storyboard"] = artifact


STAGE = Stage(name="storyboard", is_brain=True, build=build, merge=merge, check=check)

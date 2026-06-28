"""publish (BRAIN, metadata only — no uploads).

Per-platform titles/descriptions/tags + a thumbnail brief. Validator checks the
character/count limits from the show bible.
"""

from __future__ import annotations

import json

from orchestration.context import StageContext
from orchestration.stages import Stage

SCHEMA = {
    "type": "object",
    "required": ["platforms"],
    "additionalProperties": True,
    "properties": {
        "platforms": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["title", "description"],
                "additionalProperties": True,
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "thumbnail_brief": {"type": "string"},
    },
}


def build(ctx: StageContext) -> tuple[str, dict]:
    limits = ctx.bible.get("platform_metadata", {})
    instruction = (
        "Author publish.json — per-platform metadata (no uploads):\n"
        "- `platforms`: one entry per export platform with { title, description, "
        "tags[] }.\n"
        "- `thumbnail_brief`: one or two sentences describing the thumbnail.\n"
        "Stay within the platform limits below.\n\n"
        f"Platform limits:\n{json.dumps(limits, indent=2)}\n\n"
        f"Angle:\n{json.dumps(ctx.manifest.get('angle', {}), indent=2)}"
    )
    return instruction, SCHEMA


def check(ctx: StageContext, artifact: dict) -> list[str]:
    limits = ctx.bible.get("platform_metadata", {})
    errors: list[str] = []
    for platform, meta in artifact.get("platforms", {}).items():
        lim = limits.get(platform)
        if not lim:
            continue
        if len(meta.get("title", "")) > lim.get("title_max", 10_000):
            errors.append(f"{platform}: title exceeds {lim['title_max']} chars")
        if len(meta.get("description", "")) > lim.get("description_max", 10_000):
            errors.append(f"{platform}: description exceeds {lim['description_max']} chars")
        if len(meta.get("tags", [])) > lim.get("tags_max", 100):
            errors.append(f"{platform}: more than {lim['tags_max']} tags")
    return errors


def merge(ctx: StageContext, artifact: dict) -> None:
    profiles = []
    for fmt in ctx.manifest.get("format_targets", []):
        prof = {"horizontal": "yt_long", "vertical": "shorts"}.get(fmt)
        if prof and prof not in profiles:
            profiles.append(prof)
    ctx.manifest["publish"] = {**artifact, "profiles": profiles}


STAGE = Stage(name="publish", is_brain=True, build=build, merge=merge, check=check)

"""angle (BRAIN) — choose the angle, sketch the incentive structure, set the hook.

All genre flavor (positioning, hook grammar, tone) comes from the show bible;
nothing show-specific is hardcoded here.
"""

from __future__ import annotations

import json

from orchestration.context import StageContext
from orchestration.stages import Stage

SCHEMA = {
    "type": "object",
    "required": ["angle", "incentive_structure", "hook"],
    "additionalProperties": True,
    "properties": {
        "angle": {"type": "string", "minLength": 1},
        "incentive_structure": {
            "type": "object",
            "required": ["actors", "options"],
            "additionalProperties": True,
            "properties": {
                "actors": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                "options": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "payoffs": {"type": "string"},
            },
        },
        "hook": {
            "type": "object",
            "required": ["familiar_schema", "broken_variable"],
            "additionalProperties": True,
            "properties": {
                "name": {"type": "string"},
                "familiar_schema": {"type": "string", "minLength": 1},
                "broken_variable": {"type": "string", "minLength": 1},
            },
        },
    },
}


def build(ctx: StageContext) -> tuple[str, dict]:
    bible = ctx.bible
    evidence = ctx.manifest.get("evidence", [])
    instruction = (
        f"Positioning: {bible.get('positioning', '')}\n"
        f"Tone: {bible.get('tone', '')}\n\n"
        "Choose the angle for this episode and author angle.json:\n"
        "- `angle`: one sentence — the specific claim this episode makes.\n"
        "- `incentive_structure`: the actors (>=2), their options, and a short "
        "`payoffs` sketch — the game underneath the story.\n"
        "- `hook`: pick one pattern from the hook grammar and fill explicit "
        "`familiar_schema` and `broken_variable` fields.\n\n"
        f"Hook grammar:\n{json.dumps(bible.get('hook_grammar', []), indent=2)}\n\n"
        f"Evidence available ({len(evidence)} item(s)):\n"
        f"{json.dumps(evidence, indent=2)}"
    )
    return instruction, SCHEMA


def merge(ctx: StageContext, artifact: dict) -> None:
    ctx.manifest["angle"] = artifact


STAGE = Stage(name="angle", is_brain=True, build=build, merge=merge)

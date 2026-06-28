"""script (BRAIN) — VO as beats[] with emphasis markup, intent, evidence_refs.

Validator: factual beats cite >=1 evidence_ref; total reading time is a sane
fraction of the target duration. On-screen text in scenes is compression only —
that rule is enforced later (QC callout-duplication), not here.
"""

from __future__ import annotations

import json
import re

from orchestration.context import StageContext
from orchestration.stages import Stage

SCHEMA = {
    "type": "object",
    "required": ["beats"],
    "additionalProperties": False,
    "properties": {
        "beats": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["beat_id", "vo_text"],
                "additionalProperties": False,
                "properties": {
                    "beat_id": {"type": "string", "minLength": 1},
                    "vo_text": {"type": "string", "minLength": 1},
                    "intent": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


def build(ctx: StageContext) -> tuple[str, dict]:
    bible = ctx.bible
    th = bible.get("thresholds", {})
    target = th.get("target_duration_s", 90)
    instruction = (
        f"Tone: {bible.get('tone', '')}\n"
        f"Caption policy: {json.dumps(ctx.manifest.get('caption_policy', {}))}\n\n"
        "Author the VO script as script.json — `beats[]`, each "
        "{ beat_id, vo_text, intent, evidence_refs[] }:\n"
        "- VO is the full transcript; on-screen scene text is compression only "
        "(callouts/labels) — do NOT duplicate vo_text verbatim in scenes.\n"
        "- Mark emphasis with **double asterisks** inside vo_text.\n"
        "- Every factual beat (context/incentive-model/resolution) cites >=1 "
        "evidence_ref by evidence id.\n"
        f"- Aim the total reading time near {target}s "
        f"(~{th.get('reading_words_per_s', 2.6)} words/s).\n\n"
        f"Beat templates:\n{json.dumps(bible.get('beat_templates', []), indent=2)}\n\n"
        f"Angle:\n{json.dumps(ctx.manifest.get('angle', {}), indent=2)}\n\n"
        f"Evidence ids: {[e['id'] for e in ctx.manifest.get('evidence', [])]}"
    )
    return instruction, SCHEMA


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def check(ctx: StageContext, artifact: dict) -> list[str]:
    th = ctx.bible.get("thresholds", {})
    exempt = set(th.get("evidence_exempt_intents", ["hook", "implication"]))
    errors: list[str] = []
    total_words = 0
    for beat in artifact.get("beats", []):
        total_words += _word_count(beat.get("vo_text", ""))
        intent = beat.get("intent", "")
        if intent not in exempt and not beat.get("evidence_refs"):
            errors.append(
                f"beat {beat.get('beat_id')!r} (intent {intent!r}) cites no evidence_ref"
            )

    target = th.get("target_duration_s", 90)
    wps = th.get("reading_words_per_s", 2.6) or 2.6
    if target and total_words:
        est = total_words / wps
        if est < target * 0.2 or est > target * 3:
            errors.append(
                f"script reading time ~{est:.0f}s is implausible vs target {target}s "
                f"({total_words} words)"
            )
    return errors


def merge(ctx: StageContext, artifact: dict) -> None:
    ctx.manifest["script"] = artifact


STAGE = Stage(name="script", is_brain=True, build=build, merge=merge, check=check)

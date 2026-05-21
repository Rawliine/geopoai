"""broll.lib.ai_router — LTX-2.3 vs Wan 2.2.

The router answers one question: given a shot spec that the decision matrix
says is AI-eligible, which model should generate it?

Rule, per ``recap(1).md`` §5:
* Wan 2.2 when the shot foregrounds a human face that needs to read as real.
* LTX-2.3 for everything else (default — faster, cheaper, plenty good for
  aerials / cityscapes / atmospheric / conceptual).

The rule is heuristic — face detection happens on text, not pixels (we
don't have the clip yet). Phase 3+ could swap in a smarter classifier; the
interface (a string returned from :func:`pick_model`) doesn't change.

Override
--------
``shot_spec["_ai_model"]`` always wins. Set it to ``"ltx-2.3"`` or
``"wan-2.2"`` to force a model regardless of intent. The router rejects
unknown values to catch typos early.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .errors import BrollError

log = logging.getLogger("broll.ai_router")

MODEL_LTX = "ltx-2.3"
MODEL_WAN = "wan-2.2"
MODEL_FLUX_LTX = "flux-ltx"

KNOWN_MODELS: set[str] = {MODEL_LTX, MODEL_WAN, MODEL_FLUX_LTX}

PIPELINE_FLUX_LTX_I2V = "flux_ltx_i2v"

# Words that strongly suggest a face/person foreground. Lowercased substring
# match against intent + tone + negative_intent. Conservative — false
# positives push toward Wan which is fine; false negatives push toward LTX
# and risk uncanny-face output.
_FACE_HINTS = (
    "face", "faces", "facial",
    "portrait", "portraits",
    "headshot", "head-shot", "head shot",
    "talking head", "interview",
    "speaker", "speaking", "speaks",
    "smile", "smiling",
    "eye contact", "looking at camera",
    "close-up of a person", "closeup of a person",
    "person speaking", "people speaking",
    "crying", "laughing",
)

# Heuristic positive hints for LTX (kept short — these don't usually matter
# because LTX is the default, but explicit aerial/landscape language can
# defeat a borderline face match).
_NON_FACE_HINTS = (
    "aerial", "drone shot", "overhead",
    "landscape", "cityscape", "skyline",
    "abstract", "conceptual",
    "wide shot of",
)


def _intent_blob(shot_spec: dict[str, Any]) -> str:
    parts = [
        str(shot_spec.get("intent") or ""),
        str(shot_spec.get("tone") or ""),
        str(shot_spec.get("negative_intent") or ""),  # negatives push the other way; see below
    ]
    return " ".join(parts).lower()


def _explicit_override(shot_spec: dict[str, Any]) -> str | None:
    explicit = shot_spec.get("_ai_model")
    if explicit is None:
        return None
    if explicit not in KNOWN_MODELS:
        raise BrollError(
            f"shot_spec._ai_model={explicit!r} is unknown; valid: {sorted(KNOWN_MODELS)}"
        )
    return explicit


def pick_pipeline(shot_spec: dict[str, Any]) -> str | None:
    """Return ``flux_ltx_i2v`` when shot_spec requests the chained pipeline."""
    pipeline = shot_spec.get("_pipeline")
    if pipeline is None:
        return None
    if pipeline == PIPELINE_FLUX_LTX_I2V:
        return PIPELINE_FLUX_LTX_I2V
    raise BrollError(f"shot_spec._pipeline={pipeline!r} is unknown")


def pick_ai_model(shot_spec: dict[str, Any]) -> str:
    """Pick the AI source module key (``ltx-2.3``, ``wan-2.2``, ``flux-ltx``)."""
    if pick_pipeline(shot_spec) == PIPELINE_FLUX_LTX_I2V:
        log.info(
            "ai_router pick %s for shot_id=%s (flux_ltx_i2v pipeline)",
            MODEL_FLUX_LTX, shot_spec.get("shot_id"),
        )
        return MODEL_FLUX_LTX
    return pick_model(shot_spec)


def pick_model(shot_spec: dict[str, Any]) -> str:
    """Return ``"ltx-2.3"`` or ``"wan-2.2"`` for ``shot_spec``.

    Decision flow:
    1. ``_ai_model`` override → return it (validated).
    2. Any face/person hint in intent → Wan.
       Exception: if intent ALSO contains a strong non-face cue (aerial,
       cityscape, abstract), LTX wins — those framings keep faces small
       enough that LTX's weaker face fidelity won't be visible.
    3. Otherwise → LTX.
    """
    explicit = _explicit_override(shot_spec)
    if explicit is not None:
        log.info("ai_router pick %s for shot_id=%s (explicit override)",
                 explicit, shot_spec.get("shot_id"))
        return explicit

    blob = _intent_blob(shot_spec)
    has_face = any(_word_match(h, blob) for h in _FACE_HINTS)
    has_non_face = any(_word_match(h, blob) for h in _NON_FACE_HINTS)

    if has_face and not has_non_face:
        log.info(
            "ai_router pick %s for shot_id=%s (face/person hint matched)",
            MODEL_WAN, shot_spec.get("shot_id"),
        )
        return MODEL_WAN

    log.info(
        "ai_router pick %s for shot_id=%s (default, face=%s, non_face=%s)",
        MODEL_LTX, shot_spec.get("shot_id"), has_face, has_non_face,
    )
    return MODEL_LTX


def _word_match(needle: str, hay: str) -> bool:
    """Match ``needle`` as a whole-word phrase within ``hay``.

    Avoids ``"face"`` matching ``"surface"``.
    """
    pattern = r"(?<![A-Za-z])" + re.escape(needle) + r"(?![A-Za-z])"
    return re.search(pattern, hay) is not None

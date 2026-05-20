"""broll.lib.verify — two-stage candidate verification.

Stage 1: :mod:`clip_prefilter` ranks candidates (CLIP or heuristic) and we
slice to ``top_k`` (default 5).
Stage 2: :mod:`vision_verifier` picks one (Claude vision when available,
heuristic otherwise) or rejects all.

The orchestrator (``pipeline/broll.py``) calls :func:`pick` and receives a
:class:`VerifyOutcome`. On reject_all, Phase 3 escalates to the LLM
refinement loop; Phase 1 surfaces it as ``VerificationError``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..sources._base import SearchResult
from . import clip_prefilter, vision_verifier
from .errors import VerificationError

log = logging.getLogger("broll.verify")


@dataclass(slots=True)
class VerifyOutcome:
    """The verifier's full report — both stages, both verdicts."""

    winner: SearchResult | None
    prefilter_scores: list[clip_prefilter.ScoredCandidate]
    verdict: vision_verifier.VerifierVerdict
    top_k: int

    @property
    def passed(self) -> bool:
        return self.winner is not None

    def verification_block(self) -> dict[str, Any]:
        """Shape this outcome into the asset_meta ``verification`` field.

        Returns ``None`` if neither stage produced a meaningful score (e.g.
        empty candidate list).
        """
        if not self.prefilter_scores:
            return None  # type: ignore[return-value]
        # If the winner is set, surface its prefilter score; otherwise the top one.
        if self.winner is not None:
            for sc in self.prefilter_scores:
                if sc.result.id == self.winner.id and sc.result.source_name == self.winner.source_name:
                    clip_score_raw = sc.score
                    break
            else:
                clip_score_raw = self.prefilter_scores[0].score
        else:
            clip_score_raw = self.prefilter_scores[0].score
        # Clamp to [0, 1] — the schema enforces that range for clip_score.
        clip_score = max(0.0, min(1.0, clip_score_raw / 2.0 if clip_score_raw > 1 else clip_score_raw))
        return {
            "clip_score": round(clip_score, 4),
            "vision_llm_passed": self.verdict.passed,
            "vision_llm_reason": self.verdict.reason,
            "verifier_model": self.verdict.model,
        }


def pick(
    intent: str,
    candidates: list[SearchResult],
    *,
    top_k: int = 5,
    prefilter_backend: clip_prefilter.PrefilterBackend | None = None,
    verifier_backend: vision_verifier.VisionVerifier | None = None,
) -> VerifyOutcome:
    """Run both verification stages and return the assembled outcome.

    The function never raises — callers inspect ``outcome.passed``. Use
    :func:`require_pass` for an exception-flavoured API.
    """
    if not candidates:
        return VerifyOutcome(
            winner=None,
            prefilter_scores=[],
            verdict=vision_verifier.VerifierVerdict(None, "empty candidate list", "n/a"),
            top_k=top_k,
        )

    pf_backend = prefilter_backend or clip_prefilter.load_backend()
    scored = pf_backend.score(intent, candidates)
    short = scored[:top_k]
    log.info(
        "prefilter (%s) ranked %d candidates; top-%d head=[%s]",
        pf_backend.name, len(scored), len(short),
        ", ".join(f"{s.result.source_name}/{s.result.id}:{s.score:.3f}" for s in short),
    )

    vf_backend = verifier_backend or vision_verifier.load_backend()
    verdict = vf_backend.verify(intent, short)
    log.info("verifier (%s) verdict=%s reason=%s", vf_backend.name,
             "PICK" if verdict.passed else "REJECT_ALL", verdict.reason)

    winner: SearchResult | None = None
    if verdict.selected_index is not None and 0 <= verdict.selected_index < len(short):
        winner = short[verdict.selected_index].result

    return VerifyOutcome(
        winner=winner,
        prefilter_scores=scored,
        verdict=verdict,
        top_k=top_k,
    )


def require_pass(outcome: VerifyOutcome) -> SearchResult:
    """Return the winning result or raise :class:`VerificationError`."""
    if outcome.winner is None:
        raise VerificationError(
            f"verifier rejected all candidates: {outcome.verdict.reason}"
        )
    return outcome.winner

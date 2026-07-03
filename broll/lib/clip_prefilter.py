"""broll.lib.clip_prefilter — cheap candidate prefilter.

The cascade may produce 10+ candidates per shot; verifying them all with a
vision-LLM is expensive. This module reduces a candidate list to a ranked
``top_k`` (default 5) so the verifier only spends API calls on plausible
matches.

Two backends
------------
1. **CLIP** (``OpenCLIPPrefilter``): if ``open_clip`` + ``torch`` are
   installed and at least one model is loadable, we compute real
   text↔thumbnail cosine similarity. Highest quality, requires ~600 MB of
   weights and a couple seconds of warmup.
2. **Heuristic** (``HeuristicPrefilter``, default): no extra deps. Scores
   each candidate by token overlap between the shot intent and the
   candidate's ``title + description + attribution_text + tags``, plus a
   small per-source prior reflecting the AGENT.md cascade philosophy (named
   content scores Wikimedia/LoC higher; generic establishing scores Pexels
   higher).

The heuristic isn't a CLIP substitute — it can't tell whether a thumbnail
*looks* right — but it does usefully reorder candidates so the verifier sees
better matches first, and it lets Phase 1 ship without forcing torch into
``requirements.txt``. Phase 5+ swaps in CLIP via :func:`load_backend`.

Contract
--------
::

    score(intent: str, candidates: list[SearchResult]) -> list[ScoredCandidate]

Always returns the full list sorted by score descending. The verify
orchestrator slices ``[:top_k]``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

from ..sources._base import SearchResult

log = logging.getLogger("broll.clip_prefilter")


@dataclass(slots=True, frozen=True)
class ScoredCandidate:
    """A candidate plus its prefilter score (higher = better)."""

    result: SearchResult
    score: float
    backend: str


class PrefilterBackend(Protocol):
    name: str

    def score(self, intent: str, candidates: list[SearchResult]) -> list[ScoredCandidate]: ...


# ── Heuristic backend ────────────────────────────────────────────────────────

# Tiny English stopword list. We don't strip these for matching — they hurt
# precision; instead we down-weight extremely-common tokens via tf-idf style.
_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for",
    "with", "by", "from", "into", "over", "under", "as", "is", "are", "be",
    "this", "that", "these", "those", "view", "shot", "footage", "clip",
    "video", "image", "scene",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokens(s: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s or "") if len(t) > 1]


# Per-source priors. Small (+0.05 to +0.15) so they nudge, not dominate.
# Aligns with recap(1).md §2 — Wikimedia/LoC preferred for archival and
# named content; Pexels/Pixabay for generic modern.
_SOURCE_PRIOR_NAMED = {
    "wikimedia":   0.15,
    "loc":         0.12,
    "archive_org": 0.05,
    "pexels":      0.00,
    "pixabay":     -0.02,
}
_SOURCE_PRIOR_GENERIC = {
    "wikimedia":   0.00,
    "loc":         0.00,
    "archive_org": 0.00,
    "pexels":      0.10,
    "pixabay":     0.08,
}


_NAMED_HINT_RE = re.compile(
    r"\b("
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"        # multi-word proper noun ("Red Square")
    r"|\d{4}"                                # year
    r"|[A-Z]{3,}"                            # acronym
    r")"
)


def _is_named_intent(intent: str) -> bool:
    return bool(_NAMED_HINT_RE.search(intent))


class HeuristicPrefilter:
    """Token-overlap + per-source prior scoring. No deps beyond stdlib."""

    name = "heuristic"

    def score(self, intent: str, candidates: list[SearchResult]) -> list[ScoredCandidate]:
        intent_tokens = [t for t in _tokens(intent) if t not in _STOPWORDS]
        intent_set = set(intent_tokens)
        if not intent_set:
            # Degenerate intent (stopwords only). Preserve input order.
            return [ScoredCandidate(c, 0.0, self.name) for c in candidates]

        priors = _SOURCE_PRIOR_NAMED if _is_named_intent(intent) else _SOURCE_PRIOR_GENERIC
        # Light "IDF" — tokens appearing in many candidates count less.
        doc_freq: dict[str, int] = {}
        per_cand_tokens: list[set[str]] = []
        for c in candidates:
            _tags = c.source_metadata.get("tags", [])
            _tags = _tags if isinstance(_tags, list) else [_tags]
            # Any field can come back as a list from a stock API — str-ify all.
            blob = " ".join(str(x) for x in [c.title or "", c.description or "",
                                             c.attribution_text or "", *_tags])
            toks = set(_tokens(blob))
            per_cand_tokens.append(toks)
            for t in toks:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        n = max(len(candidates), 1)
        scored: list[ScoredCandidate] = []
        for c, toks in zip(candidates, per_cand_tokens):
            if not toks:
                base = 0.0
            else:
                overlap = intent_set & toks
                weight = 0.0
                for t in overlap:
                    # Down-weight tokens that appear in many candidates.
                    df = doc_freq.get(t, 1)
                    weight += 1.0 + (1.0 - df / n) * 0.5
                base = weight / max(len(intent_set), 1)

            prior = priors.get(c.source_name, 0.0)
            # Penalty when license is unclear — we'd refuse to fetch anyway.
            penalty = -0.5 if c.license.get("type") == "unclear" else 0.0
            score = base + prior + penalty
            scored.append(ScoredCandidate(c, score, self.name))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored


# ── Optional OpenCLIP backend ────────────────────────────────────────────────
class OpenCLIPPrefilter:
    """Real CLIP scoring via open_clip + torch.

    Loaded lazily so Python startup is fast when this backend isn't used.
    Caches the model on the instance. Falls back to heuristic if a thumbnail
    can't be fetched / decoded.
    """

    name = "open_clip"

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai") -> None:
        import open_clip  # type: ignore
        import torch  # type: ignore

        self._torch = torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self._model = self._model.to(self._device).eval()
        self._tokenizer = open_clip.get_tokenizer(model_name)

    def _embed_image(self, url: str):
        import io
        import urllib.request
        from PIL import Image  # type: ignore
        req = urllib.request.Request(url, headers={"User-Agent": "GeoPoAI-broll/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        tensor = self._preprocess(img).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            return self._model.encode_image(tensor)

    def score(self, intent: str, candidates: list[SearchResult]) -> list[ScoredCandidate]:
        if not candidates:
            return []
        with self._torch.no_grad():
            text = self._tokenizer([intent]).to(self._device)
            text_features = self._model.encode_text(text)
            text_features /= text_features.norm(dim=-1, keepdim=True)

        scored: list[ScoredCandidate] = []
        for c in candidates:
            if not c.thumbnail_url:
                scored.append(ScoredCandidate(c, 0.0, self.name))
                continue
            try:
                img_features = self._embed_image(c.thumbnail_url)
                img_features = img_features / img_features.norm(dim=-1, keepdim=True)
                sim = float((text_features @ img_features.T).item())
            except Exception as exc:  # noqa: BLE001
                log.warning("open_clip embedding failed for %s/%s: %s",
                            c.source_name, c.id, exc)
                sim = 0.0
            scored.append(ScoredCandidate(c, sim, self.name))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored


# ── Loader ───────────────────────────────────────────────────────────────────
def load_backend(prefer: str | None = None) -> PrefilterBackend:
    """Return the best available backend.

    ``prefer="heuristic"`` forces the heuristic path. ``prefer="open_clip"``
    insists on CLIP and raises if it's not importable. The default tries CLIP
    when ``BROLL_USE_CLIP=1``; otherwise heuristic.
    """
    pref = prefer or os.environ.get("BROLL_PREFILTER", "")
    if pref == "heuristic":
        return HeuristicPrefilter()
    want_clip = pref == "open_clip" or os.environ.get("BROLL_USE_CLIP") == "1"
    if want_clip:
        try:
            return OpenCLIPPrefilter()
        except ImportError as exc:
            if pref == "open_clip":
                raise
            log.info("open_clip not available (%s); falling back to heuristic", exc)
    return HeuristicPrefilter()


def score(
    intent: str,
    candidates: list[SearchResult],
    *,
    backend: PrefilterBackend | None = None,
) -> list[ScoredCandidate]:
    """Convenience wrapper — most callers should use :mod:`broll.lib.verify` instead."""
    b = backend or load_backend()
    return b.score(intent, candidates)

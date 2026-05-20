"""broll.lib.keyword_generator — shot intent → stock-search keyword queries.

The orchestrator's LLM may pre-seed ``shot_spec.queries``. When it doesn't
(or doesn't seed enough), the cascade calls this module to expand intent into
N short query strings suitable for stock-source search APIs.

Phase 0 ships:
* A deterministic heuristic generator (no network, no API key) that produces
  reasonable variants by manipulating the intent string. This is good enough
  for smoke tests and as a fallback when the LLM path is unavailable.
* A pluggable ``LLMClient`` protocol so Phase 1 can swap in Claude or a local
  model without touching call sites.

Both paths obey the same contract:

    generate_queries(intent, *, n=4, llm_client=None, existing=None) -> list[str]

* ``existing`` queries (e.g. ones the orchestrator already provided) are
  preserved verbatim and de-duped against new candidates.
* The returned list contains between 1 and ``n`` queries, trimmed and unique.
* Never returns empty unless the intent is empty.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Protocol

log = logging.getLogger("broll.keyword_generator")

# ── Heuristic generator ──────────────────────────────────────────────────────

# Short list of high-signal words that, if present, are worth keeping as a
# narrower variant. The goal is variety, not linguistic correctness.
_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for",
    "with", "by", "from", "into", "over", "under", "as", "is", "are", "be",
    "this", "that", "these", "those", "view", "shot", "footage", "clip",
    "video", "image",
}

_TIME_OF_DAY = {"dawn", "dusk", "sunrise", "sunset", "morning", "evening", "night", "noon", "midday", "afternoon"}
_PERSPECTIVE = {"aerial", "drone", "overhead", "topdown", "top-down", "closeup", "close-up", "wide", "establishing"}


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9'\-]+", s.strip().lower()) if t]


def _content_tokens(toks: list[str]) -> list[str]:
    return [t for t in toks if t not in _STOPWORDS]


def _join(toks: Iterable[str]) -> str:
    return " ".join(t for t in toks if t).strip()


def _heuristic_variants(intent: str, n: int) -> list[str]:
    """Produce up to ``n`` keyword variants from a free-text intent.

    Strategy (cheap and predictable):
        1. Strip stopwords → bag of content words.
        2. Pick out perspective / time-of-day tokens if any.
        3. Variant A: original intent, condensed (stopwords removed).
        4. Variant B: content words minus perspective markers (broader).
        5. Variant C: first 3-4 content words only (narrowest).
        6. Variant D: pair perspective + nouns (if perspective exists).

    All variants are de-duped and truncated to ``n``.
    """
    toks = _tokens(intent)
    if not toks:
        return []

    content = _content_tokens(toks)
    perspective = [t for t in content if t in _PERSPECTIVE]
    time_words = [t for t in content if t in _TIME_OF_DAY]
    nouns_ish = [t for t in content if t not in _PERSPECTIVE and t not in _TIME_OF_DAY]

    candidates: list[str] = []
    # A — condensed
    candidates.append(_join(content))
    # B — drop perspective/time, keep subject
    if perspective or time_words:
        candidates.append(_join(nouns_ish))
    # C — first 3 content words
    if len(content) > 3:
        candidates.append(_join(content[:3]))
    # D — perspective + first 2 nouns
    if perspective and nouns_ish:
        candidates.append(_join(perspective[:1] + nouns_ish[:2]))
    # E — time + subject
    if time_words and nouns_ish:
        candidates.append(_join(nouns_ish[:2] + time_words[:1]))

    # De-dup preserving order, trim to n.
    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= n:
            break
    return out


# ── LLM hook (interface stub for Phase 1) ────────────────────────────────────
class LLMClient(Protocol):
    """Minimal interface a Phase-1 LLM client must satisfy.

    Implementations live outside this module (e.g. broll/lib/llm_claude.py).
    """

    def expand_queries(self, intent: str, *, n: int) -> list[str]:  # pragma: no cover - protocol
        ...


def generate_queries(
    intent: str,
    *,
    n: int = 4,
    llm_client: LLMClient | None = None,
    existing: list[str] | None = None,
) -> list[str]:
    """Return up to ``n`` keyword queries for the given intent.

    If ``llm_client`` is provided it is used first; the heuristic fills any
    remaining slots so the cascade always has at least one query as long as
    ``intent`` contains content words.

    ``existing`` queries are kept verbatim at the front of the result and
    counted against the budget.
    """
    if n <= 0:
        return []
    intent = (intent or "").strip()

    out: list[str] = []
    seen: set[str] = set()

    def _push(q: str) -> None:
        q = q.strip()
        if q and q.lower() not in seen and len(out) < n:
            seen.add(q.lower())
            out.append(q)

    for q in existing or ():
        _push(q)

    if llm_client is not None and len(out) < n:
        try:
            for q in llm_client.expand_queries(intent, n=n - len(out)):
                _push(q)
        except Exception:
            log.warning("LLM keyword expansion failed; falling back to heuristic", exc_info=True)

    if len(out) < n and intent:
        for q in _heuristic_variants(intent, n=n - len(out)):
            _push(q)

    return out

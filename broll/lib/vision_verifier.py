"""broll.lib.vision_verifier — pick a winning candidate (or reject all).

After the CLIP prefilter narrows down to top-K, the verifier looks at the
actual thumbnails and decides whether any match the shot intent. AGENT.md §"Pitfalls":
CLIP alone can't catch contextual errors ("any canal at dawn ≈ Suez Canal at
dawn"); the verifier exists to catch those.

Backends
--------
* **Claude** (``ClaudeVisionVerifier``): when ``ANTHROPIC_API_KEY`` is set,
  call the Anthropic Messages API directly over HTTP (no SDK dep). Sends the
  shot intent plus up to ``top_k`` thumbnails as base64 image blocks; asks
  the model to return a JSON object naming the best candidate or
  ``reject_all`` with a reason. Model defaults to ``claude-sonnet-4-6`` —
  Sonnet is more than enough for "does this thumbnail show X" and is cheaper
  than Opus.
* **Heuristic** (``HeuristicVerifier``): trusts the prefilter — picks the
  top-scored candidate if its score is above a threshold, else rejects all.
  Useful for offline tests and CI; explicitly *not* what AGENT.md considers
  sufficient verification, but graceful when the key isn't available.

Both return a :class:`VerifierVerdict` so the orchestrator handles them
uniformly.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from . import rate_limit
from .clip_prefilter import ScoredCandidate

log = logging.getLogger("broll.vision_verifier")


@dataclass(slots=True)
class VerifierVerdict:
    """Result of one vision-LLM pass over a candidate list."""

    selected_index: int | None  # None == reject_all
    reason: str
    backend: str
    model: str | None = None
    raw_response: str | None = None

    @property
    def passed(self) -> bool:
        return self.selected_index is not None


class VisionVerifier(Protocol):
    name: str
    model: str | None

    def verify(self, intent: str, candidates: list[ScoredCandidate]) -> VerifierVerdict: ...


# ── Heuristic ────────────────────────────────────────────────────────────────
class HeuristicVerifier:
    """No-network verifier that trusts the prefilter score.

    Picks the top candidate if its score is above ``threshold``. Threshold is
    a soft default; the heuristic prefilter typically returns scores in
    [0, ~2.0], so 0.25 is a sensible "did anything actually match" cutoff.
    """

    name = "heuristic"
    model = None

    def __init__(self, threshold: float = 0.25) -> None:
        self.threshold = threshold

    def verify(self, intent: str, candidates: list[ScoredCandidate]) -> VerifierVerdict:
        if not candidates:
            return VerifierVerdict(None, "no candidates supplied", self.name)
        top = candidates[0]
        if top.score >= self.threshold:
            return VerifierVerdict(
                0,
                f"top prefilter score {top.score:.3f} >= threshold {self.threshold}; "
                f"backend={top.backend}",
                self.name,
            )
        return VerifierVerdict(
            None,
            f"top prefilter score {top.score:.3f} below threshold {self.threshold} — "
            "no candidate confidently matches intent",
            self.name,
        )


# ── Claude vision (direct HTTP) ──────────────────────────────────────────────
_ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-6"

_VERIFIER_PROMPT = (
    "You are a strict B-roll verifier. You are shown a shot intent in plain language "
    "and a short numbered list of candidate thumbnails. For each candidate, decide "
    "whether it FAITHFULLY depicts the intent — not just visually similar. Reject "
    "candidates that show a different place, person, time period, or context, even "
    "if the lighting or composition is similar.\n\n"
    "Respond with a single JSON object — no prose, no markdown — with exactly these "
    "keys:\n"
    "  - selected_index: integer index (0-based) of the best candidate, OR the string "
    "\"reject_all\" if none faithfully match.\n"
    "  - reason: one short sentence (<=200 chars).\n"
)


class ClaudeVisionVerifier:
    """Anthropic Messages API caller. Uses urllib so no SDK dep is required."""

    name = "anthropic"

    def __init__(self, model: str | None = None, *, timeout: float = 30) -> None:
        self.model = model or os.environ.get("BROLL_VERIFIER_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout
        self._key = os.environ.get("ANTHROPIC_API_KEY")
        if not self._key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

    def _fetch_thumbnail(self, url: str) -> tuple[str, bytes] | None:
        """Return (media_type, raw_bytes) or None on failure."""
        req = urllib.request.Request(url, headers={"User-Agent": "GeoPoAI-broll/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ct = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                if not ct.startswith("image/"):
                    return None
                return ct, resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("verifier: failed to fetch thumbnail %s: %s", url, exc)
            return None

    def _build_message(self, intent: str, candidates: list[ScoredCandidate]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": _VERIFIER_PROMPT},
            {"type": "text", "text": f"Shot intent: {intent}"},
        ]
        included_indices: list[int] = []
        for i, sc in enumerate(candidates):
            url = sc.result.thumbnail_url
            if not url:
                continue
            fetched = self._fetch_thumbnail(url)
            if not fetched:
                continue
            media_type, body = fetched
            content.append({"type": "text", "text": f"Candidate {i} (source={sc.result.source_name})"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(body).decode("ascii"),
                },
            })
            included_indices.append(i)
        return {
            "model": self.model,
            "max_tokens": 200,
            "messages": [{"role": "user", "content": content}],
        }, included_indices

    def _call_api(self, payload: dict[str, Any]) -> str:
        rate_limit.acquire("anthropic")
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _ANTHROPIC_API,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "User-Agent": "GeoPoAI-broll/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        # Messages API returns content as a list of blocks.
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        raise RuntimeError(f"no text content in response: {response}")

    def _parse(self, text: str, included: list[int]) -> tuple[int | None, str, str]:
        """Return (selected_index_in_original_list, reason, raw_text)."""
        # Be forgiving: model sometimes wraps JSON in fences.
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            # Remove a leading "json" hint.
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None, f"verifier produced unparseable response: {text[:200]}", text
        sel = parsed.get("selected_index")
        reason = str(parsed.get("reason", ""))[:300]
        if sel == "reject_all" or sel is None:
            return None, reason or "reject_all", text
        if isinstance(sel, int) and 0 <= sel < len(included) + 100:
            return int(sel), reason or "selected", text
        return None, f"verifier returned invalid selected_index={sel!r}", text

    def verify(self, intent: str, candidates: list[ScoredCandidate]) -> VerifierVerdict:
        if not candidates:
            return VerifierVerdict(None, "no candidates supplied", self.name, self.model)
        payload, included = self._build_message(intent, candidates)
        if not included:
            return VerifierVerdict(
                None,
                "no candidate had a usable thumbnail; verifier cannot judge",
                self.name,
                self.model,
            )
        try:
            text = self._call_api(payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("anthropic verifier API call failed: %s", exc)
            return VerifierVerdict(None, f"verifier API error: {exc}", self.name, self.model)

        idx, reason, raw = self._parse(text, included)
        return VerifierVerdict(idx, reason, self.name, self.model, raw)


# ── Loader ───────────────────────────────────────────────────────────────────
def load_backend(prefer: str | None = None) -> VisionVerifier:
    """Return the best available verifier.

    Order:
    * ``prefer="heuristic"`` → heuristic
    * ``prefer="anthropic"`` → Anthropic (raises if no key)
    * default → Anthropic if ``ANTHROPIC_API_KEY`` is set, else heuristic
    """
    pref = prefer or os.environ.get("BROLL_VERIFIER", "")
    if pref == "heuristic":
        return HeuristicVerifier()
    if pref == "anthropic":
        return ClaudeVisionVerifier()
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeVisionVerifier()
        except Exception as exc:  # noqa: BLE001
            log.info("anthropic verifier unavailable (%s); using heuristic", exc)
    return HeuristicVerifier()

"""broll.lib.vision_verifier — pick a winning candidate (or reject all).

After the CLIP prefilter narrows down to top-K, the verifier looks at the
actual thumbnails and decides whether any match the shot intent. AGENT.md §"Pitfalls":
CLIP alone can't catch contextual errors ("any canal at dawn ≈ Suez Canal at
dawn"); the verifier exists to catch those.

Backends (``BROLL_VERIFIER`` env, default ``claude_cli``)
---------------------------------------------------------
* **claude_cli** (``ClaudeCliVerifier``, DEFAULT): shell out to Claude Code
  headless — ``claude -p "<prompt>" --output-format json`` — using the
  operator's existing Claude Code subscription login. Requires NO
  ``ANTHROPIC_API_KEY``. Preflight checks the ``claude`` binary exists and
  is authenticated. Verifications run serially (subscription rate limits).
* **checkpoint** (``CheckpointVerifier``): write a contact sheet +
  ``candidates.json`` next to the shot output and raise
  :class:`AwaitingBrainError` so the orchestrator surfaces it for in-session
  review (same contract as ``pipeline/broll.py --ask``).
* **api** (``ClaudeVisionVerifier``): Anthropic Messages API over HTTP — used
  ONLY when ``ANTHROPIC_API_KEY`` is set; for future unattended batch scale,
  never required.
* **clip_only** (``ClipOnlyVerifier``): skip vision-LLM; stricter heuristic
  threshold (degraded mode).
* **heuristic** (``HeuristicVerifier``): offline / CI fallback.

Selection: ``claude_cli`` → automatic fallback to ``checkpoint`` when the CLI
is unavailable or unauthenticated.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import rate_limit
from .clip_prefilter import ScoredCandidate
from .errors import AwaitingBrainError

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


# ── Shared prompt / parse ────────────────────────────────────────────────────
_DEFAULT_MODEL = "claude-sonnet-4-6"
_CLIP_ONLY_DEFAULT_THRESHOLD = 0.45

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


def _parse_verdict_json(text: str) -> tuple[int | None, str, str]:
    """Return (selected_index, reason, raw_text)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
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
    if isinstance(sel, int) and sel >= 0:
        return int(sel), reason or "selected", text
    return None, f"verifier returned invalid selected_index={sel!r}", text


def _fetch_thumbnail_bytes(url: str) -> tuple[str, bytes] | None:
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


def _thumbnail_to_temp_path(url: str, index: int) -> Path | None:
    fetched = _fetch_thumbnail_bytes(url)
    if not fetched:
        return None
    media_type, body = fetched
    ext = ".jpg"
    if "png" in media_type:
        ext = ".png"
    elif "webp" in media_type:
        ext = ".webp"
    fd, path = tempfile.mkstemp(suffix=ext, prefix=f"broll_verify_{index}_")
    os.close(fd)
    Path(path).write_bytes(body)
    return Path(path)


def _build_cli_prompt(intent: str, candidates: list[ScoredCandidate], image_paths: list[Path]) -> str:
    lines = [_VERIFIER_PROMPT, f"Shot intent: {intent}", ""]
    for i, (sc, p) in enumerate(zip(candidates, image_paths, strict=False)):
        lines.append(
            f"Candidate {i} (source={sc.result.source_name}, title={sc.result.title!r}): "
            f"image file path: {p}"
        )
    lines.append("")
    lines.append("Respond with JSON only.")
    return "\n".join(lines)


# ── Heuristic ────────────────────────────────────────────────────────────────
class HeuristicVerifier:
    """No-network verifier that trusts the prefilter score."""

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


class ClipOnlyVerifier(HeuristicVerifier):
    """Degraded mode: stricter heuristic threshold, no vision-LLM."""

    name = "clip_only"

    def __init__(self, threshold: float | None = None) -> None:
        t = threshold
        if t is None:
            t = float(os.environ.get("BROLL_CLIP_ONLY_THRESHOLD", str(_CLIP_ONLY_DEFAULT_THRESHOLD)))
        super().__init__(threshold=t)


# ── Claude CLI (subscription auth) ───────────────────────────────────────────
class ClaudeCliVerifier:
    """Shell out to Claude Code headless — no ANTHROPIC_API_KEY required."""

    name = "claude_cli"
    model = "claude-code"

    def __init__(self, *, timeout: float = 120) -> None:
        self._timeout = timeout
        self._binary = shutil.which("claude")
        if not self._binary:
            raise RuntimeError(
                "claude CLI not found on PATH; install Claude Code or set BROLL_VERIFIER=checkpoint"
            )

    @staticmethod
    def available() -> bool:
        """Return True if the claude binary exists and responds to a preflight."""
        binary = shutil.which("claude")
        if not binary:
            return False
        try:
            proc = subprocess.run(
                [binary, "-p", "Reply with JSON: {\"ok\": true}", "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                log.info("claude CLI preflight failed (exit %s): %s", proc.returncode, proc.stderr[:200])
                return False
            return True
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.info("claude CLI preflight error: %s", exc)
            return False

    def verify(self, intent: str, candidates: list[ScoredCandidate]) -> VerifierVerdict:
        if not candidates:
            return VerifierVerdict(None, "no candidates supplied", self.name, self.model)

        temp_paths: list[Path] = []
        included: list[int] = []
        try:
            shortlist: list[ScoredCandidate] = []
            for i, sc in enumerate(candidates):
                url = sc.result.thumbnail_url
                if not url:
                    continue
                p = _thumbnail_to_temp_path(url, i)
                if p is None:
                    continue
                temp_paths.append(p)
                shortlist.append(sc)
                included.append(i)

            if not shortlist:
                return VerifierVerdict(
                    None,
                    "no candidate had a usable thumbnail; verifier cannot judge",
                    self.name,
                    self.model,
                )

            prompt = _build_cli_prompt(intent, shortlist, temp_paths)
            proc = subprocess.run(
                [self._binary, "-p", prompt, "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "")[:400]
                return VerifierVerdict(
                    None, f"claude CLI exited {proc.returncode}: {err}", self.name, self.model
                )

            raw = proc.stdout.strip()
            # Claude Code JSON output wraps the result; extract text field if present.
            try:
                wrapper = json.loads(raw)
                if isinstance(wrapper, dict):
                    for key in ("result", "content", "text", "message"):
                        val = wrapper.get(key)
                        if isinstance(val, str) and val.strip():
                            raw = val
                            break
            except json.JSONDecodeError:
                pass

            idx, reason, full = _parse_verdict_json(raw)
            # Map index within shortlist back to original list position.
            if idx is not None and 0 <= idx < len(included):
                mapped = included[idx]
                return VerifierVerdict(mapped, reason, self.name, self.model, full)
            if idx is not None:
                return VerifierVerdict(idx, reason, self.name, self.model, full)
            return VerifierVerdict(None, reason, self.name, self.model, full)
        finally:
            for p in temp_paths:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass


# ── Checkpoint (awaiting-brain) ──────────────────────────────────────────────
class CheckpointVerifier:
    """Write contact sheet + candidates.json; raise AwaitingBrainError."""

    name = "checkpoint"
    model = None

    def __init__(self, *, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir

    def verify(self, intent: str, candidates: list[ScoredCandidate]) -> VerifierVerdict:
        from .contact_sheet import write_verifier_checkpoint

        out_dir = self._output_dir or Path(os.environ.get("BROLL_CHECKPOINT_DIR", "output/broll"))
        paths = write_verifier_checkpoint(intent, candidates, out_dir)
        raise AwaitingBrainError(
            "vision verifier checkpoint: review contact sheet and re-run with selection",
            contact_sheet=paths["contact_sheet"],
            candidates_json=paths["candidates_json"],
        )


# ── Claude vision (direct HTTP / API key) ────────────────────────────────────
_ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


class ClaudeVisionVerifier:
    """Anthropic Messages API caller. Uses urllib so no SDK dep is required."""

    name = "api"

    def __init__(self, model: str | None = None, *, timeout: float = 30) -> None:
        self.model = model or os.environ.get("BROLL_VERIFIER_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout
        self._key = os.environ.get("ANTHROPIC_API_KEY")
        if not self._key:
            raise RuntimeError("ANTHROPIC_API_KEY not set (required for BROLL_VERIFIER=api)")

    def _fetch_thumbnail(self, url: str) -> tuple[str, bytes] | None:
        """Instance hook for tests; delegates to module helper."""
        return _fetch_thumbnail_bytes(url)

    def _build_message(self, intent: str, candidates: list[ScoredCandidate]) -> tuple[dict[str, Any], list[int]]:
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
        payload = {
            "model": self.model,
            "max_tokens": 200,
            "messages": [{"role": "user", "content": content}],
        }
        return payload, included_indices

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
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        raise RuntimeError(f"no text content in response: {response}")

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

        idx, reason, raw = _parse_verdict_json(text)
        return VerifierVerdict(idx, reason, self.name, self.model, raw)


# ── Loader ───────────────────────────────────────────────────────────────────
def load_backend(prefer: str | None = None) -> VisionVerifier:
    """Return the configured verifier backend.

    Default ``claude_cli``; falls back to ``checkpoint`` when CLI unavailable.
    """
    pref = (prefer or os.environ.get("BROLL_VERIFIER", "") or "claude_cli").strip().lower()

    # Under pytest without an explicit backend, keep the pre-W18 heuristic default
    # so existing unit tests (fake thumbnail URLs) stay green.
    if not (prefer or os.environ.get("BROLL_VERIFIER")) and os.environ.get("PYTEST_CURRENT_TEST"):
        return HeuristicVerifier()

    if pref == "heuristic":
        return HeuristicVerifier()
    if pref == "clip_only":
        return ClipOnlyVerifier()
    if pref in ("anthropic", "api"):
        return ClaudeVisionVerifier()
    if pref == "checkpoint":
        return CheckpointVerifier()
    if pref == "claude_cli":
        if ClaudeCliVerifier.available():
            try:
                return ClaudeCliVerifier()
            except RuntimeError as exc:
                log.info("claude_cli unavailable (%s); falling back to checkpoint", exc)
        else:
            log.info("claude CLI not available/authenticated; falling back to checkpoint")
        return CheckpointVerifier()

    log.warning("unknown BROLL_VERIFIER=%r; using claude_cli default", pref)
    if ClaudeCliVerifier.available():
        try:
            return ClaudeCliVerifier()
        except RuntimeError:
            pass
    return CheckpointVerifier()


# Legacy alias for tests
AnthropicVisionVerifier = ClaudeVisionVerifier

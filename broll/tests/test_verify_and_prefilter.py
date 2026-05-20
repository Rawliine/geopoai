"""CLIP prefilter heuristic + verify orchestrator."""

from __future__ import annotations

import json
from typing import Any

import pytest

from broll.lib import clip_prefilter, verify, vision_verifier
from broll.sources._base import SearchResult


def _result(source: str, id_: str, *, title: str = "", description: str = "",
            license_type: str = "cc-by", tags: list[str] | None = None) -> SearchResult:
    return SearchResult(
        id=id_, source_name=source,
        thumbnail_url=f"https://t/{id_}.jpg",
        download_url=f"https://d/{id_}.mp4",
        license={"type": license_type, "attribution_required": True, "commercial_use_ok": True},
        attribution_text="x", title=title, description=description,
        source_metadata={"tags": tags or []},
    )


# ── Heuristic prefilter ─────────────────────────────────────────────────────
def test_heuristic_ranks_overlap_highest() -> None:
    pf = clip_prefilter.HeuristicPrefilter()
    cs = [
        _result("pexels", "1", title="random kittens"),
        _result("wikimedia", "2", title="Suez Canal container ship aerial dawn"),
        _result("pexels", "3", title="container ship at sea"),
    ]
    scored = pf.score("aerial container ships at the Suez Canal at dawn", cs)
    assert scored[0].result.id == "2"
    assert scored[-1].result.id == "1"


def test_heuristic_named_intent_uses_named_prior() -> None:
    pf = clip_prefilter.HeuristicPrefilter()
    cs = [_result("pexels", "p", title="generic ships"),
          _result("wikimedia", "w", title="generic ships")]
    scored = pf.score("Red Square Moscow", cs)
    # Both have identical overlap, but Wikimedia's prior wins on named intent.
    assert scored[0].result.source_name == "wikimedia"


def test_heuristic_unclear_license_penalized() -> None:
    pf = clip_prefilter.HeuristicPrefilter()
    cs = [_result("loc", "a", title="x", license_type="pd"),
          _result("loc", "b", title="x x x", license_type="unclear")]
    scored = pf.score("x", cs)
    assert scored[0].result.license["type"] == "pd"


def test_heuristic_empty_intent_preserves_order() -> None:
    pf = clip_prefilter.HeuristicPrefilter()
    cs = [_result("a", "1"), _result("b", "2")]
    scored = pf.score("the of and", cs)
    assert [s.result.id for s in scored] == ["1", "2"]


# ── load_backend ────────────────────────────────────────────────────────────
def test_load_backend_default_is_heuristic(monkeypatch) -> None:
    monkeypatch.delenv("BROLL_USE_CLIP", raising=False)
    monkeypatch.delenv("BROLL_PREFILTER", raising=False)
    assert clip_prefilter.load_backend().name == "heuristic"


def test_load_backend_forced_clip_raises_without_install(monkeypatch) -> None:
    with pytest.raises(ImportError):
        clip_prefilter.load_backend("open_clip")


# ── Heuristic verifier ──────────────────────────────────────────────────────
def test_heuristic_verifier_picks_top_when_above_threshold() -> None:
    v = vision_verifier.HeuristicVerifier(threshold=0.1)
    scored = [
        clip_prefilter.ScoredCandidate(_result("p", "1", title="x"), 0.5, "heuristic"),
        clip_prefilter.ScoredCandidate(_result("p", "2", title="x"), 0.4, "heuristic"),
    ]
    verdict = v.verify("intent", scored)
    assert verdict.passed and verdict.selected_index == 0


def test_heuristic_verifier_rejects_below_threshold() -> None:
    v = vision_verifier.HeuristicVerifier(threshold=0.9)
    scored = [clip_prefilter.ScoredCandidate(_result("p", "1"), 0.1, "heuristic")]
    verdict = v.verify("intent", scored)
    assert not verdict.passed
    assert verdict.selected_index is None


def test_heuristic_verifier_empty_input() -> None:
    v = vision_verifier.HeuristicVerifier()
    verdict = v.verify("intent", [])
    assert not verdict.passed


# ── Verify orchestrator ─────────────────────────────────────────────────────
def test_pick_passes_with_strong_prefilter_signal() -> None:
    candidates = [
        _result("pexels", "good", title="container ship aerial at sea"),
        _result("pexels", "bad",  title="cute puppies"),
    ]
    outcome = verify.pick("aerial container ship at sea", candidates)
    assert outcome.passed
    assert outcome.winner.id == "good"
    block = outcome.verification_block()
    assert 0.0 <= block["clip_score"] <= 1.0
    assert block["vision_llm_passed"] is True


def test_pick_returns_reject_when_no_match() -> None:
    candidates = [_result("p", "1", title="anything else")]
    # Force a very high threshold so heuristic verifier rejects.
    outcome = verify.pick(
        "completely unrelated topic xyz123",
        candidates,
        verifier_backend=vision_verifier.HeuristicVerifier(threshold=10.0),
    )
    assert not outcome.passed
    assert outcome.winner is None


def test_pick_no_candidates() -> None:
    outcome = verify.pick("anything", [])
    assert not outcome.passed
    block = outcome.verification_block()
    assert block is None


# ── Claude verifier (mocked HTTP) ───────────────────────────────────────────
def test_claude_verifier_parses_json_response(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    v = vision_verifier.ClaudeVisionVerifier(model="claude-test")

    # Skip the real thumbnail fetch.
    monkeypatch.setattr(v, "_fetch_thumbnail", lambda url: ("image/jpeg", b"\x00\x01"))
    # Stub the API call.
    monkeypatch.setattr(
        v, "_call_api",
        lambda payload: json.dumps({"selected_index": 0, "reason": "matches dawn aerial"}),
    )
    cs = [clip_prefilter.ScoredCandidate(_result("p", "1", title="x"), 0.5, "heuristic"),
          clip_prefilter.ScoredCandidate(_result("p", "2", title="y"), 0.4, "heuristic")]
    verdict = v.verify("intent", cs)
    assert verdict.passed and verdict.selected_index == 0
    assert "dawn" in verdict.reason


def test_claude_verifier_handles_reject_all(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    v = vision_verifier.ClaudeVisionVerifier(model="claude-test")
    monkeypatch.setattr(v, "_fetch_thumbnail", lambda url: ("image/jpeg", b"\x00\x01"))
    monkeypatch.setattr(
        v, "_call_api",
        lambda payload: '```json\n{"selected_index": "reject_all", "reason": "wrong place"}\n```',
    )
    cs = [clip_prefilter.ScoredCandidate(_result("p", "1"), 0.5, "heuristic")]
    verdict = v.verify("intent", cs)
    assert not verdict.passed
    assert verdict.reason == "wrong place"


def test_claude_verifier_api_failure(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    v = vision_verifier.ClaudeVisionVerifier(model="claude-test")
    monkeypatch.setattr(v, "_fetch_thumbnail", lambda url: ("image/jpeg", b"\x00\x01"))
    def boom(payload): raise RuntimeError("503")
    monkeypatch.setattr(v, "_call_api", boom)
    cs = [clip_prefilter.ScoredCandidate(_result("p", "1"), 0.5, "heuristic")]
    verdict = v.verify("intent", cs)
    assert not verdict.passed
    assert "503" in verdict.reason

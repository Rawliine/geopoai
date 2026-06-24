"""Phase 2 strategy routing through ``pipeline/broll.py``.

Each strategy is exercised end-to-end with both sources mocked at the
module level. Real APIs are never called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from broll.sources import AI_SOURCES, SOURCES
from broll.sources._ai_base import AIGenerationError
from broll.sources._base import SearchResult


def _stock_candidate(source: str = "wikimedia") -> SearchResult:
    return SearchResult(
        id=f"id-{source}", source_name=source,
        thumbnail_url="https://t/x.jpg",
        download_url="<INVALID — should be replaced>",
        license={"type": "pd", "attribution_required": False, "commercial_use_ok": True},
        attribution_text="t", title="container ship aerial",
        source_metadata={"page_url": "p"},
    )


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    monkeypatch.setenv("BROLL_NO_CACHE", "1")
    monkeypatch.setenv("BROLL_NO_AI_CACHE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pipeline import broll as pipeline_broll
    monkeypatch.setattr(pipeline_broll, "_OUTPUT_DIR", tmp_path / "output")
    return tmp_path


def _stub_all_stock(monkeypatch, *, return_results=()) -> None:
    for s in SOURCES:
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, _r=return_results, **k: list(_r))


def _stub_ai_success(monkeypatch, target_meta: dict | None = None):
    """Replace both AI sources with a stub returning a synthetic meta + writing a file."""
    calls = {"count": 0}

    def fake_generate(spec, target_path, *, verification=None, client=None):
        calls["count"] += 1
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(b"FAKE_AI")
        meta_path = Path(str(target_path) + ".meta.json")
        meta = target_meta or {
            "shot_id": spec["shot_id"],
            "asset_path": str(target_path),
            "kind": "ai_video",
            "source": {"name": "ltx-2.3", "version": "2.3",
                       "url": "comfyui://test", "fetched_at": "2026-05-20T00:00:00Z"},
            "license": {"type": "ai_generated", "attribution_required": False,
                        "commercial_use_ok": True, "attribution_text": None},
            "verification": None,
            "ai_metadata": {"model": "ltx-2.3", "prompt": spec["intent"], "seed": 1, "lora_stack": []},
            "modifications": [],
        }
        meta_path.write_text(json.dumps(meta))
        return meta

    for name in AI_SOURCES:
        monkeypatch.setattr(AI_SOURCES[name], "generate", fake_generate)
    return calls


def _stub_ai_failure(monkeypatch):
    def boom(spec, target_path, *, verification=None, client=None):
        raise AIGenerationError("simulated AI failure")
    for name in AI_SOURCES:
        monkeypatch.setattr(AI_SOURCES[name], "generate", boom)


def _spec(kind: str, **overrides) -> dict:
    base = {
        "shot_id": "phase2-001",
        "intent": "an aerial of mountains at dawn",
        "kind": kind,
        "duration_seconds": 4,
        "format": "horizontal",
    }
    base.update(overrides)
    return base


# ── ai_only ─────────────────────────────────────────────────────────────────
def test_ai_only_calls_ai_directly(monkeypatch, tmp_path) -> None:
    _stub_all_stock(monkeypatch)
    calls = _stub_ai_success(monkeypatch)
    from pipeline import broll as pipeline_broll
    meta = pipeline_broll.run_shot(_spec("conceptual"))
    assert meta["source"]["name"] == "ltx-2.3"
    assert calls["count"] == 1


def test_ai_only_failure_surfaces(monkeypatch) -> None:
    _stub_all_stock(monkeypatch)
    _stub_ai_failure(monkeypatch)
    from pipeline import broll as pipeline_broll
    with pytest.raises(AIGenerationError):
        pipeline_broll.run_shot(_spec("conceptual"))


# ── ai_first ────────────────────────────────────────────────────────────────
def test_ai_first_picks_ai_when_it_works(monkeypatch) -> None:
    _stub_all_stock(monkeypatch)
    calls = _stub_ai_success(monkeypatch)
    from pipeline import broll as pipeline_broll
    # "filler" defaults to ai_first per the decision matrix.
    meta = pipeline_broll.run_shot(_spec("filler"))
    assert calls["count"] == 1
    assert meta["source"]["name"] == "ltx-2.3"


def test_ai_first_falls_back_to_stock_on_failure(monkeypatch, tmp_path) -> None:
    # Stub wikimedia to return a usable candidate; also stub the wrapper
    # download to avoid hitting the network for the real CDN URL.
    cand = _stock_candidate()
    monkeypatch.setattr(SOURCES["wikimedia"], "search", lambda *a, **k: [cand, cand, cand])
    for s in ("loc", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    _stub_ai_failure(monkeypatch)

    # Replace fetch_to_wrapper to fake the disk write.
    from broll.sources import _base as base_mod
    captured = {}
    def fake_fetch(result, target_path, *, shot_id, verification=None, extra_modifications=None):
        captured["winner"] = result
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(b"STOCK")
        return {
            "shot_id": shot_id, "asset_path": str(target_path), "kind": "stock_video",
            "source": {"name": result.source_name, "url": "p",
                       "fetched_at": "2026-05-20T00:00:00Z", "version": None},
            "license": result.license, "verification": verification,
            "ai_metadata": None, "modifications": [],
        }
    monkeypatch.setattr("pipeline.broll.fetch_to_wrapper", fake_fetch)

    from pipeline import broll as pipeline_broll
    meta = pipeline_broll.run_shot(_spec("filler"))
    assert meta["source"]["name"] == "wikimedia"
    assert captured["winner"].source_name == "wikimedia"


# ── stock_first with AI fallback ────────────────────────────────────────────
def test_stock_first_falls_back_to_ai_when_cascade_empty(monkeypatch) -> None:
    _stub_all_stock(monkeypatch, return_results=())  # nothing
    calls = _stub_ai_success(monkeypatch)
    from pipeline import broll as pipeline_broll
    meta = pipeline_broll.run_shot(_spec("establishing"))
    assert calls["count"] == 1
    assert meta["source"]["name"] == "ltx-2.3"


def test_stock_first_no_ai_allowed_raises(monkeypatch) -> None:
    _stub_all_stock(monkeypatch, return_results=())
    _stub_ai_failure(monkeypatch)
    from pipeline import broll as pipeline_broll
    from broll.lib.errors import NoCandidatesError
    # stock_only kind: AI is forbidden.
    with pytest.raises(NoCandidatesError):
        pipeline_broll.run_shot(_spec("real_named_event"))


# ── stock_only ──────────────────────────────────────────────────────────────
def test_stock_only_does_not_call_ai(monkeypatch, tmp_path) -> None:
    cand = _stock_candidate()
    monkeypatch.setattr(SOURCES["wikimedia"], "search", lambda *a, **k: [cand, cand, cand])
    for s in ("loc", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    ai_calls = _stub_ai_success(monkeypatch)

    def fake_fetch(result, target_path, *, shot_id, verification=None, extra_modifications=None):
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(b"STOCK")
        return {
            "shot_id": shot_id, "asset_path": str(target_path), "kind": "stock_video",
            "source": {"name": result.source_name, "url": "p",
                       "fetched_at": "2026-05-20T00:00:00Z", "version": None},
            "license": result.license, "verification": verification,
            "ai_metadata": None, "modifications": [],
        }
    monkeypatch.setattr("pipeline.broll.fetch_to_wrapper", fake_fetch)

    from pipeline import broll as pipeline_broll
    meta = pipeline_broll.run_shot(_spec("real_named_event"))
    assert meta["source"]["name"] == "wikimedia"
    assert ai_calls["count"] == 0


# ── log.json contents ───────────────────────────────────────────────────────
def test_log_records_strategy_and_outcome(monkeypatch, tmp_path) -> None:
    _stub_all_stock(monkeypatch)
    _stub_ai_success(monkeypatch)
    from pipeline import broll as pipeline_broll
    pipeline_broll.run_shot(_spec("conceptual"))
    log_path = pipeline_broll._OUTPUT_DIR / "phase2-001.log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text())
    assert log["decision"]["strategy"] == "ai_only"
    assert log["outcome"] == "ai_only"
    assert log["ai"]["model"] in ("ltx-2.3", "wan-2.2")

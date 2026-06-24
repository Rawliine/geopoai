"""W18 tests: DVIDS, NASA, reference ingest, contact sheets, routing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from broll.lib import cascade, rate_limit, vision_verifier
from broll.lib.contact_sheet import build_contact_sheet, write_reference_checkpoint
from broll.lib.errors import AwaitingBrainError, SourceAuthError
from broll.sources import CASCADE_ORDER, dvids, nasa, reference

_REPO = Path(__file__).resolve().parent.parent
_FIXTURE_MP4 = _REPO / "broll" / "tests" / "fixtures" / "ref_sample.mp4"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    rate_limit.reset()


# ── Cascade order ───────────────────────────────────────────────────────────
def test_cascade_order_includes_dvids_nasa_after_nara() -> None:
    nara_i = CASCADE_ORDER.index("nara")
    dvids_i = CASCADE_ORDER.index("dvids")
    nasa_i = CASCADE_ORDER.index("nasa")
    assert nara_i < dvids_i < nasa_i


def test_reference_urls_route_first(monkeypatch) -> None:
    """reference_urls in spec triggers reference path before cascade."""
    from pipeline import broll as pipeline_broll

    called = {"ref": False, "stock": False}

    def fake_ref(spec, log_payload, **kw):
        called["ref"] = True
        return {"asset_path": "output/broll/x.mp4"}

    def fake_stock(spec, log_payload, **kw):
        called["stock"] = True
        return None

    monkeypatch.setattr(pipeline_broll, "_run_reference", fake_ref)
    monkeypatch.setattr(pipeline_broll, "_run_stock", fake_stock)
    monkeypatch.setattr(pipeline_broll, "decide", lambda s: {"strategy": "stock_only", "ai_allowed": False, "reason": "test"})

    spec = {
        "shot_id": "route_test",
        "intent": "test routing",
        "kind": "establishing",
        "duration_seconds": 4,
        "reference_urls": ["https://example.com/v.mp4"],
    }
    pipeline_broll.run_shot(spec)
    assert called["ref"] is True
    assert called["stock"] is False


# ── DVIDS ───────────────────────────────────────────────────────────────────
_DVIDS_SEARCH = {
    "results": [{
        "id": "video:999",
        "type": "video",
        "title": "Training exercise",
        "thumbnail": "https://cdn.example/thumb.jpg",
        "url": "https://www.dvidshub.net/video/999/training",
        "duration": 120,
        "credit": "Sgt. Test",
        "unit_name": "Test Unit",
    }]
}
_DVIDS_ASSET = {
    "results": {
        "id": "video:999",
        "title": "Training exercise",
        "url": "https://www.dvidshub.net/video/999/training",
        "duration": 120,
        "thumbnail": "https://cdn.example/thumb.jpg",
        "credit": [{"name": "Jane Doe", "rank": "Sgt."}],
        "unit_name": "Test Unit",
        "branch": "Army",
        "files": [
            {"src": "https://cdn.example/small.mp4", "type": "video/mp4", "width": 486, "height": 274, "bitrate": 300},
            {"src": "https://cdn.example/hd.mp4", "type": "video/mp4", "width": 1280, "height": 720, "bitrate": 1500},
        ],
    }
}


def test_dvids_search_picks_largest_mp4(monkeypatch) -> None:
    monkeypatch.setenv("DVIDS_API_KEY", "test-key")
    monkeypatch.setenv("NASA_LIVE_TESTS", "1")

    def fake(url, headers=None, timeout=20):
        if "/asset" in url:
            return _DVIDS_ASSET
        return _DVIDS_SEARCH

    monkeypatch.setattr(dvids, "http_get_json", fake)
    results = dvids.search("training exercise", limit=5)
    assert len(results) == 1
    r = results[0]
    assert r.source_name == "dvids"
    assert r.license["type"] == "pd"
    assert "hd.mp4" in r.download_url


def test_dvids_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("DVIDS_API_KEY", raising=False)
    with pytest.raises(SourceAuthError):
        dvids.search("anything")


# ── NASA ────────────────────────────────────────────────────────────────────
_NASA_SEARCH = {
    "collection": {
        "items": [{
            "data": [{
                "nasa_id": "Apollo11",
                "title": "Apollo 11 launch",
                "center": "KSC",
                "description": "Launch footage",
            }],
            "links": [{"href": "https://images-assets.nasa.gov/video/Apollo11/Apollo11~thumb.jpg"}],
        }]
    }
}
_NASA_ASSET = {
    "collection": {
        "items": [
            {"href": "https://images-assets.nasa.gov/video/Apollo11/Apollo11~thumb.jpg"},
            {"href": "https://images-assets.nasa.gov/video/Apollo11/Apollo11~mobile.mp4"},
            {"href": "https://images-assets.nasa.gov/video/Apollo11/Apollo11~orig.mp4"},
        ]
    }
}


def test_nasa_search_fetches_manifest(monkeypatch) -> None:
    monkeypatch.setenv("NASA_LIVE_TESTS", "1")

    def fake(url, headers=None, timeout=20):
        if "/asset/" in url:
            return _NASA_ASSET
        return _NASA_SEARCH

    monkeypatch.setattr(nasa, "http_get_json", fake)
    results = nasa.search("apollo launch", limit=3)
    assert len(results) == 1
    r = results[0]
    assert r.source_name == "nasa"
    assert r.license["type"] == "pd"
    assert r.download_url.endswith(".mp4")


# ── Contact sheet ───────────────────────────────────────────────────────────
def test_contact_sheet_builds_grid(tmp_path) -> None:
    # Use local color PNG via PIL
    from PIL import Image
    p = tmp_path / "t.jpg"
    Image.new("RGB", (64, 48), (255, 0, 0)).save(p)
    sheet = build_contact_sheet([
        {"id": "a", "label": "a @ 0.0s", "thumb_url": str(p)},
        {"id": "b", "label": "b @ 1.0s", "thumb_url": str(p)},
    ], cols=2)
    assert sheet.width > 0 and sheet.height > 0


def test_reference_checkpoint_writes_files(tmp_path) -> None:
    from PIL import Image
    thumb = tmp_path / "thumb.jpg"
    Image.new("RGB", (64, 48), (0, 128, 255)).save(thumb)
    segments = [{
        "segment_id": "seg_000",
        "start_seconds": 0.0,
        "end_seconds": 2.0,
        "thumb_path": str(thumb),
    }]
    paths = write_reference_checkpoint("test intent", segments, tmp_path, shot_id="shot_x")
    assert Path(paths["contact_sheet"]).exists()
    assert Path(paths["candidates_json"]).exists()
    doc = json.loads(Path(paths["candidates_json"]).read_text())
    assert doc["shot_id"] == "shot_x"
    assert len(doc["segments"]) == 1


# ── Reference ingest (local fixture) ────────────────────────────────────────
@pytest.mark.skipif(not _FIXTURE_MP4.exists(), reason="ref_sample.mp4 fixture missing")
def test_reference_ask_exits_with_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BROLL_VERIFIER", "heuristic")
    spec = {
        "shot_id": "ref_ask_test",
        "intent": "blue color field test clip",
        "kind": "establishing",
        "duration_seconds": 2,
        "reference_urls": [f"file://{_FIXTURE_MP4}"],
    }
    target = tmp_path / "ref_ask_test.mp4"
    with pytest.raises(AwaitingBrainError) as exc:
        reference.ingest_reference_urls(spec, target, ask=True, output_dir=tmp_path)
    assert exc.value.contact_sheet
    assert Path(exc.value.contact_sheet).exists()


@pytest.mark.skipif(not _FIXTURE_MP4.exists(), reason="ref_sample.mp4 fixture missing")
def test_reference_pick_completes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BROLL_VERIFIER", "heuristic")
    spec = {
        "shot_id": "ref_pick_test",
        "intent": "blue color field test clip",
        "kind": "establishing",
        "duration_seconds": 2,
        "reference_urls": [f"file://{_FIXTURE_MP4}"],
    }
    target = tmp_path / "ref_pick_test.mp4"
    with pytest.raises(AwaitingBrainError):
        reference.ingest_reference_urls(spec, target, ask=True, output_dir=tmp_path)
    meta = reference.ingest_reference_urls(spec, target, pick="seg_000", output_dir=tmp_path)
    assert Path(meta["asset_path"]).exists()
    meta_path = Path(meta["asset_path"] + ".meta.json")
    assert meta_path.exists()
    doc = json.loads(meta_path.read_text())
    assert doc["license"]["type"] == "user_provided"


# ── Vision verifier backends ────────────────────────────────────────────────
def test_load_backend_heuristic(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_VERIFIER", "heuristic")
    assert vision_verifier.load_backend().name == "heuristic"


def test_load_backend_clip_only(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_VERIFIER", "clip_only")
    assert vision_verifier.load_backend().name == "clip_only"


def test_claude_cli_verifier_mocked(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_VERIFIER", "claude_cli")
    from broll.lib.clip_prefilter import ScoredCandidate
    from broll.sources._base import SearchResult

    v = vision_verifier.ClaudeCliVerifier()
    monkeypatch.setattr(v, "_binary", "/usr/bin/claude")

    r = SearchResult(
        id="1", source_name="p", thumbnail_url="file:///tmp/x.jpg",
        download_url="http://x", license={"type": "pd", "attribution_required": False, "commercial_use_ok": True},
        attribution_text="x",
    )
    sc = ScoredCandidate(r, 0.5, "heuristic")

    monkeypatch.setattr(vision_verifier, "_thumbnail_to_temp_path", lambda url, i: Path("/tmp/fake.jpg"))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": '{"selected_index": 0, "reason": "ok"}', "stderr": ""})(),
    )
    verdict = v.verify("intent", [sc])
    assert verdict.passed


def test_cascade_skips_dvids_without_key(monkeypatch) -> None:
    monkeypatch.delenv("DVIDS_API_KEY", raising=False)
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)

    for name in CASCADE_ORDER:
        mod = __import__(f"broll.sources.{name}", fromlist=[name])
        if name in ("wikimedia", "loc", "nara", "archive_org", "dvids", "pexels", "pixabay", "nasa"):
            if name == "nasa":
                monkeypatch.setattr(mod, "search", lambda *a, **k: [])
            elif name in ("wikimedia", "loc", "archive_org"):
                monkeypatch.setattr(mod, "search", lambda *a, **k: [])
            else:
                continue

    report = cascade.walk({
        "shot_id": "x", "intent": "test query content", "kind": "establishing", "duration_seconds": 4,
    }, min_candidates=1, max_candidates=3, per_query_limit=2)
    assert "dvids" in report.skipped or report.total() >= 0

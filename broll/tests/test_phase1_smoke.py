"""Phase-1 end-to-end smoke tests.

Two flavours:

1. **Hermetic full-pipeline** (always runs): mocks every source and verifier
   so the whole orchestrator (cascade → verify → wrapper) is exercised
   without touching the network. This is the "your local CI" path.

2. **Network smoke per source** (gated on availability): one canned query per
   source. Skips quietly if the source requires a missing key. Marked
   ``network`` so it's only run on explicit opt-in.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from broll.sources._base import SearchResult

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")


# ── Hermetic full-pipeline ──────────────────────────────────────────────────
class _Handler(http.server.BaseHTTPRequestHandler):
    BODY = b"FAKE_MP4_" + b"x" * 8192

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(self.BODY)))
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, *args, **kwargs) -> None:
        pass


@pytest.fixture(scope="module")
def fake_cdn():
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()
            t.join(timeout=2)


def _candidate(cdn_root: str, title: str, source: str = "pexels", id_: str = "1") -> SearchResult:
    return SearchResult(
        id=id_, source_name=source,
        thumbnail_url=f"{cdn_root}/t.jpg",
        download_url=f"{cdn_root}/v.mp4",
        license={"type": "pexels", "attribution_required": False,
                 "attribution_text": "Test", "commercial_use_ok": True},
        attribution_text="Test", title=title, description="",
        source_metadata={"page_url": f"{cdn_root}/page"},
    )


def test_hermetic_full_pipeline(monkeypatch, tmp_path, fake_cdn) -> None:
    """Mocks: every source returns canned candidates; verifier uses heuristic;
    asset is downloaded from a local HTTP server."""
    from broll.sources import SOURCES
    from broll.lib import rate_limit
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    monkeypatch.setenv("BROLL_NO_CACHE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # force heuristic verifier
    rate_limit.reset()

    candidates = [
        _candidate(fake_cdn, "container ship aerial at sea", source="wikimedia", id_="wm1"),
        _candidate(fake_cdn, "random kittens",                source="pexels",    id_="px1"),
    ]
    monkeypatch.setattr(SOURCES["wikimedia"], "search", lambda q, limit, **k: [candidates[0]])
    for s in ("loc", "nara", "archive_org", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    monkeypatch.setattr(SOURCES["pexels"], "search", lambda q, limit, **k: [candidates[1]])

    from pipeline import broll as pipeline_broll
    monkeypatch.setattr(pipeline_broll, "_OUTPUT_DIR", tmp_path)

    spec = {
        "shot_id": "hermetic-001",
        "intent": "container ship aerial at sea",
        "kind": "establishing",
        "duration_seconds": 4,
        "format": "horizontal",
        "queries": ["container ship aerial"],
        "stock_first": True,
    }
    meta = pipeline_broll.run_shot(spec)

    assert meta["shot_id"] == "hermetic-001"
    assert meta["source"]["name"] == "wikimedia"  # winner picked by heuristic
    assert meta["verification"]["vision_llm_passed"] is True
    asset = tmp_path / "hermetic-001.mp4"
    assert asset.exists() and asset.stat().st_size > 0
    log = tmp_path / "hermetic-001.log.json"
    assert log.exists()
    log_doc = json.loads(log.read_text())
    assert log_doc["outcome"] == "fetched"
    assert "wikimedia" in log_doc["cascade"]["by_source"]


def test_hermetic_reject_all_writes_log(monkeypatch, tmp_path) -> None:
    from broll.sources import SOURCES
    from broll.lib import rate_limit, vision_verifier
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    monkeypatch.setenv("BROLL_NO_CACHE", "1")
    rate_limit.reset()

    # Provide one candidate but force verifier to reject everything.
    cand = SearchResult(
        id="x", source_name="pexels",
        thumbnail_url="https://t/x.jpg",
        download_url="https://d/x.mp4",
        license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
        attribution_text="t", title="unrelated",
        source_metadata={"page_url": "p"},
    )
    monkeypatch.setattr(SOURCES["pexels"], "search", lambda *a, **k: [cand])
    for s in ("wikimedia", "loc", "nara", "archive_org", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])

    # Force a strict heuristic verifier.
    monkeypatch.setattr(vision_verifier, "load_backend",
                        lambda prefer=None: vision_verifier.HeuristicVerifier(threshold=99.0))

    from pipeline import broll as pipeline_broll
    monkeypatch.setattr(pipeline_broll, "_OUTPUT_DIR", tmp_path)

    spec = {
        "shot_id": "reject-001",
        "intent": "Suez Canal aerial container shipping",
        "kind": "establishing",
        "duration_seconds": 4,
        "format": "horizontal",
        "queries": ["Suez Canal aerial"],
    }
    with pytest.raises(Exception):
        pipeline_broll.run_shot(spec)

    log_path = tmp_path / "reject-001.log.json"
    assert log_path.exists()
    log_doc = json.loads(log_path.read_text())
    assert log_doc["outcome"] == "reject_all"


# ── Live network smoke per source ───────────────────────────────────────────
pytestmark_network = pytest.mark.network


@pytest.mark.network
@pytest.mark.parametrize(
    "source_name, query, needs_env",
    [
        ("wikimedia",   "Suez Canal",          None),
        ("loc",         "earth from space",    None),
        ("nara",        "moon landing",        "NARA_API_KEY"),
        ("archive_org", "1940 newsreel",       None),
        ("pexels",      "container ship",      "PEXELS_API_KEY"),
        ("pixabay",     "ocean drone",         "PIXABAY_API_KEY"),
    ],
)
def test_live_source_returns_results(source_name, query, needs_env) -> None:
    if needs_env and not os.environ.get(needs_env):
        pytest.skip(f"{needs_env} not set")
    from broll.sources import SOURCES
    mod = SOURCES[source_name]
    results = mod.search(query, limit=3)
    # Network can flake; the smoke proves the request path itself is sane,
    # not that any specific query has results. So we only assert no exceptions
    # and that results are a list.
    assert isinstance(results, list)
    # When we DO get results, every one must have a download URL.
    for r in results:
        assert r.download_url, f"{source_name} returned a candidate with no download_url"
        assert r.source_name == source_name


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("PEXELS_API_KEY"), reason="PEXELS_API_KEY not set")
def test_live_cascade_to_fetch(tmp_path, monkeypatch) -> None:
    """End-to-end: cascade with real APIs, fetch the winner."""
    from pipeline import broll as pipeline_broll
    monkeypatch.setattr(pipeline_broll, "_OUTPUT_DIR", tmp_path)
    spec = json.loads((ROOT / "scripts" / "broll" / "test_shot.json").read_text())
    spec["shot_id"] = "phase1-live-001"
    meta = pipeline_broll.run_shot(spec)
    assert meta["shot_id"] == "phase1-live-001"
    asset = tmp_path / "phase1-live-001.mp4"
    assert asset.exists() and asset.stat().st_size > 0

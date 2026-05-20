"""asset_wrapper atomic-write + meta-validation behaviour.

Network paths use a tiny local HTTP server so the test stays offline.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
from pathlib import Path

import pytest

from broll.lib import asset_wrapper
from broll.lib.errors import AssetWrapperError, SchemaValidationError


# ── Local HTTP fixture ───────────────────────────────────────────────────────
class _Handler(http.server.BaseHTTPRequestHandler):
    BODY = b"FAKE_VIDEO_BYTES_" + b"x" * 1024

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ok.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.BODY)))
            self.end_headers()
            self.wfile.write(self.BODY)
        elif self.path == "/big.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.end_headers()
            self.wfile.write(b"x" * (5 * 1024 * 1024))
        elif self.path == "/notfound":
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs) -> None:  # silence
        pass


@pytest.fixture(scope="module")
def http_server():
    handler = _Handler
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()
            thread.join(timeout=2)


# ── Happy path ───────────────────────────────────────────────────────────────
def test_download_writes_asset_and_meta(http_server, tmp_path: Path) -> None:
    target = tmp_path / "shotA.mp4"
    meta = asset_wrapper.download(
        f"{http_server}/ok.mp4",
        target,
        shot_id="shotA",
        kind="stock_video",
        source={"name": "pexels", "version": None},
        license={
            "type": "pexels",
            "attribution_required": False,
            "attribution_text": "Test attribution",
            "commercial_use_ok": True,
        },
    )

    assert target.exists()
    assert target.read_bytes() == _Handler.BODY
    meta_path = asset_wrapper.meta_path_for(target)
    assert meta_path.exists()
    on_disk = json.loads(meta_path.read_text())
    assert on_disk["shot_id"] == "shotA"
    assert on_disk["kind"] == "stock_video"
    assert on_disk["source"]["url"].endswith("/ok.mp4")
    assert on_disk["source"]["fetched_at"].endswith("Z")
    assert on_disk["ai_metadata"] is None
    assert meta == on_disk


def test_finalize_adopts_existing_file(tmp_path: Path) -> None:
    local = tmp_path / "raw.mp4"
    local.write_bytes(b"PRE_GENERATED")

    target = tmp_path / "out" / "shotF.mp4"
    meta = asset_wrapper.finalize(
        local,
        target,
        shot_id="shotF",
        kind="ai_video",
        source={
            "name": "ltx-2.3",
            "version": "2.3",
            "url": "https://verda.local/job/abc",
        },
        license={
            "type": "ai_generated",
            "attribution_required": False,
            "attribution_text": None,
            "commercial_use_ok": True,
        },
        ai_metadata={
            "model": "ltx-2.3",
            "prompt": "aerial shot, dawn lighting",
            "seed": 42,
        },
    )
    assert target.exists()
    assert target.read_bytes() == b"PRE_GENERATED"
    assert not local.exists()  # move=True by default
    assert meta["ai_metadata"]["seed"] == 42


# ── Error / rollback paths ──────────────────────────────────────────────────
def test_download_404_leaves_nothing_behind(http_server, tmp_path: Path) -> None:
    target = tmp_path / "ghost.mp4"
    with pytest.raises(AssetWrapperError):
        asset_wrapper.download(
            f"{http_server}/notfound",
            target,
            shot_id="ghost",
            kind="stock_video",
            source={"name": "pexels"},
            license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
        )
    assert not target.exists()
    assert not asset_wrapper.meta_path_for(target).exists()
    # No leftover tempfiles in the parent dir.
    assert not list(tmp_path.glob(".ghost.mp4.*"))


def test_download_size_cap_enforced(http_server, tmp_path: Path) -> None:
    target = tmp_path / "huge.mp4"
    with pytest.raises(AssetWrapperError):
        asset_wrapper.download(
            f"{http_server}/big.mp4",
            target,
            shot_id="huge",
            kind="stock_video",
            source={"name": "pexels"},
            license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
            max_bytes=64 * 1024,
        )
    assert not target.exists()


def test_unsupported_scheme_rejected(tmp_path: Path) -> None:
    with pytest.raises(AssetWrapperError):
        asset_wrapper.download(
            "file:///etc/passwd",
            tmp_path / "x.mp4",
            shot_id="x",
            kind="stock_video",
            source={"name": "pexels"},
            license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
        )


def test_invalid_meta_rolls_back_asset(http_server, tmp_path: Path) -> None:
    """If meta validation fails, the asset must not be left on disk."""
    target = tmp_path / "bad_meta.mp4"
    with pytest.raises(SchemaValidationError):
        asset_wrapper.download(
            f"{http_server}/ok.mp4",
            target,
            shot_id="bad_meta",
            kind="stock_video",
            source={"name": "pexels"},
            # Missing required `commercial_use_ok` → meta will be invalid.
            license={"type": "pexels", "attribution_required": False},
        )
    assert not target.exists()
    assert not asset_wrapper.meta_path_for(target).exists()


def test_load_meta_roundtrip(http_server, tmp_path: Path) -> None:
    target = tmp_path / "rt.mp4"
    asset_wrapper.download(
        f"{http_server}/ok.mp4",
        target,
        shot_id="rt",
        kind="stock_video",
        source={"name": "pexels"},
        license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
    )
    loaded = asset_wrapper.load_meta(target)
    assert loaded["shot_id"] == "rt"

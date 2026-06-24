"""Unit tests for every stock source. HTTP is mocked at the helper level."""

from __future__ import annotations

import os
from typing import Any

import pytest

from broll.lib import rate_limit
from broll.lib.errors import SourceAuthError
from broll.sources import archive_org, loc, pexels, pixabay, wikimedia


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    rate_limit.reset()


# ── Wikimedia ───────────────────────────────────────────────────────────────
_WIKIMEDIA_PAYLOAD = {
    "query": {
        "pages": [
            {
                "pageid": 12345,
                "title": "File:Suez Canal aerial.webm",
                "canonicalurl": "https://commons.wikimedia.org/wiki/File:Suez_Canal_aerial.webm",
                "imageinfo": [{
                    "url": "https://upload.wikimedia.org/.../Suez_Canal_aerial.webm",
                    "thumburl": "https://upload.wikimedia.org/.../thumb.jpg",
                    "mediatype": "VIDEO",
                    "width": 1920,
                    "height": 1080,
                    "user": "TestUser",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                        "Artist": {"value": "Test Author"},
                        "Credit": {"value": "Wikimedia Commons"},
                        "ImageDescription": {"value": "Aerial view of the Suez Canal at sunrise"},
                    },
                }],
            },
            # A non-video entry that should be filtered.
            {
                "pageid": 99,
                "title": "File:Not a video.jpg",
                "imageinfo": [{"url": "x", "mediatype": "BITMAP", "extmetadata": {}}],
            },
        ]
    }
}


def test_wikimedia_search_filters_to_video(monkeypatch) -> None:
    monkeypatch.setattr(wikimedia, "http_get_json", lambda *a, **k: _WIKIMEDIA_PAYLOAD)
    results = wikimedia.search("Suez Canal", limit=5)
    assert len(results) == 1
    r = results[0]
    assert r.source_name == "wikimedia"
    assert r.license["type"] == "cc-by-sa"
    assert r.license["attribution_required"] is True
    assert "Test Author" in r.attribution_text
    assert r.width == 1920


def test_wikimedia_unclear_license_refuses_fetch(monkeypatch, tmp_path) -> None:
    bad = {
        "query": {"pages": [{
            "pageid": 1, "title": "File:X.webm",
            "imageinfo": [{"url": "https://example.com/x.webm", "thumburl": "",
                           "mediatype": "VIDEO", "extmetadata": {}}],
        }]}
    }
    monkeypatch.setattr(wikimedia, "http_get_json", lambda *a, **k: bad)
    results = wikimedia.search("anything")
    assert results[0].license["type"] == "unclear"
    with pytest.raises(Exception):  # SourceError subclass
        wikimedia.fetch(results[0], tmp_path / "x.mp4", shot_id="x")


# ── LoC ─────────────────────────────────────────────────────────────────────
_LOC_PAYLOAD = {
    "results": [
        {
            "id": "https://www.loc.gov/item/00694301/",
            "title": "Buffalo dance, Hopi Indians",
            "description": "Cultural footage",
            "rights": "no known restrictions",
            "contributor": ["Edison Manufacturing Company"],
            "image_url": ["https://tile.loc.gov/.../thumb.jpg"],
            "resources": [{
                "files": [
                    {"mimetype": "video/mp4", "url": "https://tile.loc.gov/.../movie.mp4"},
                ]
            }],
            "dates": ["1898"],
            "subject": ["Hopi"],
        },
        # No video resource → filtered out.
        {
            "id": "x", "title": "x", "rights": "no known restrictions",
            "resources": [{"files": [{"mimetype": "image/jpeg", "url": "x.jpg"}]}],
        },
    ]
}


def test_loc_search_picks_mp4(monkeypatch) -> None:
    monkeypatch.setattr(loc, "http_get_json", lambda *a, **k: _LOC_PAYLOAD)
    results = loc.search("buffalo dance")
    assert len(results) == 1
    r = results[0]
    assert r.source_name == "loc"
    assert r.license["type"] == "pd"
    assert r.download_url.endswith(".mp4")


# ── Archive.org ─────────────────────────────────────────────────────────────
_ARCHIVE_SEARCH = {
    "response": {"docs": [
        {
            "identifier": "test_ok",
            "title": "PD documentary",
            "description": "...",
            "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
            "creator": "John Doe",
            "year": "1965",
        },
        # Unclear license — dropped.
        {"identifier": "bad", "title": "X", "licenseurl": None},
    ]}
}
_ARCHIVE_METADATA = {
    "files": [
        {"name": "test_ok_small.mp4", "format": "h.264", "size": "1234567"},
        {"name": "test_ok_big.mp4",   "format": "h.264", "size": "999999999"},
        {"name": "test_ok.ogv",       "format": "OGG Video", "size": "5"},
    ]
}


def test_archive_picks_smallest_mp4_and_drops_unclear(monkeypatch) -> None:
    calls = {"count": 0}
    def fake(url, headers=None, timeout=20):
        calls["count"] += 1
        if "advancedsearch" in url:
            return _ARCHIVE_SEARCH
        return _ARCHIVE_METADATA
    monkeypatch.setattr(archive_org, "http_get_json", fake)
    results = archive_org.search("documentary")
    assert len(results) == 1
    r = results[0]
    assert r.source_name == "archive_org"
    assert r.license["type"] == "pd"
    assert "test_ok_small.mp4" in r.download_url


# ── Pexels ──────────────────────────────────────────────────────────────────
def test_pexels_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with pytest.raises(SourceAuthError):
        pexels.search("anything")


_PEXELS_PAYLOAD = {
    "videos": [
        {
            "id": 5555, "url": "https://www.pexels.com/video/5555/",
            "image": "https://images.pexels.com/.../t.jpg", "duration": 12,
            "user": {"id": 1, "name": "Test Pexels User", "url": "https://www.pexels.com/@x"},
            "video_files": [
                {"link": "https://videos.pexels.com/.../hd.mp4", "quality": "hd", "width": 1920, "height": 1080, "file_type": "video/mp4"},
                {"link": "https://videos.pexels.com/.../hls.m3u8", "quality": "hls", "width": 1920, "height": 1080, "file_type": "application/vnd.apple.mpegurl"},
            ],
        },
        # HLS-only → filtered.
        {
            "id": 999, "url": "x", "video_files": [
                {"link": "x.m3u8", "quality": "hls", "file_type": "application/vnd.apple.mpegurl"},
            ],
        },
    ]
}


def test_pexels_filters_hls(monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "test")
    import urllib.request
    import io, json as _json
    class _Resp:
        headers: dict[str, str] = {}
        def __init__(self, body: bytes): self._b = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(_json.dumps(_PEXELS_PAYLOAD).encode("utf-8")))
    results = pexels.search("test", limit=5, orientation="horizontal")
    assert len(results) == 1
    assert results[0].download_url.endswith(".mp4")


# ── Pixabay ─────────────────────────────────────────────────────────────────
def test_pixabay_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    with pytest.raises(SourceAuthError):
        pixabay.search("anything")


_PIXABAY_PAYLOAD = {
    "hits": [
        {
            "id": 42, "pageURL": "https://pixabay.com/videos/42/",
            "user": "Pix User", "user_id": 5, "duration": 8, "tags": "container, ship, sea",
            "videos": {
                "large":  {"url": "https://cdn.pixabay.com/.../large.mp4",  "width": 1920, "height": 1080},
                "medium": {"url": "https://cdn.pixabay.com/.../medium.mp4", "width": 1280, "height": 720},
                "small":  {"url": "https://cdn.pixabay.com/.../small.mp4",  "width": 960,  "height": 540},
                "tiny":   {"url": "https://cdn.pixabay.com/.../tiny.mp4",   "width": 640,  "height": 360, "thumbnail": "https://i.vimeocdn.com/.../t.jpg"},
            },
        }
    ]
}


def test_pixabay_picks_largest_matching_aspect(monkeypatch) -> None:
    monkeypatch.setenv("PIXABAY_API_KEY", "test")
    monkeypatch.setattr(pixabay, "http_get_json", lambda *a, **k: _PIXABAY_PAYLOAD)
    results = pixabay.search("ship", orientation="horizontal")
    assert len(results) == 1
    assert "large.mp4" in results[0].download_url
    assert results[0].license["type"] == "pixabay"

"""Rate limiter + cache behaviour."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from broll.lib import cache, rate_limit
from broll.sources._base import SearchResult


# ── Rate limit ──────────────────────────────────────────────────────────────
def test_acquire_returns_zero_for_unknown_source(monkeypatch) -> None:
    rate_limit.reset()
    assert rate_limit.acquire("not-a-source") == 0.0


def test_bucket_blocks_when_empty(monkeypatch) -> None:
    rate_limit.reset()
    rate_limit.configure("test_src", rate_limit.RateLimit(capacity=2, refill_per_sec=4))
    # Two free acquires.
    assert rate_limit.acquire("test_src") == 0.0
    assert rate_limit.acquire("test_src") == 0.0
    # Third one must wait ~0.25s for one token.
    t0 = time.monotonic()
    rate_limit.acquire("test_src")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.2, f"expected wait ≥0.2s, got {elapsed}"


def test_env_disables_rate_limit(monkeypatch) -> None:
    rate_limit.reset()
    rate_limit.configure("test_src2", rate_limit.RateLimit(capacity=1, refill_per_sec=0.01))
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    # Even with tiny refill, env disable means no wait.
    for _ in range(5):
        assert rate_limit.acquire("test_src2") == 0.0


# ── Cache ───────────────────────────────────────────────────────────────────
def _sample_result() -> SearchResult:
    return SearchResult(
        id="abc",
        source_name="pexels",
        thumbnail_url="https://example.com/t.jpg",
        download_url="https://example.com/v.mp4",
        license={"type": "pexels", "attribution_required": False, "commercial_use_ok": True},
        attribution_text="Test",
        title="t", description="", source_metadata={"page_url": "https://example.com/"},
    )


def test_cache_disabled_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BROLL_NO_CACHE", "1")
    cache.put("src", "q", [_sample_result()], orientation=None, limit=5)
    assert cache.get("src", "q", orientation=None, limit=5) is None


def test_cache_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BROLL_NO_CACHE", raising=False)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "searches")
    cache.put("src", "alpha", [_sample_result()], orientation="horizontal", limit=5)
    got = cache.get("src", "alpha", orientation="horizontal", limit=5)
    assert got is not None and len(got) == 1
    assert got[0].id == "abc" and got[0].source_name == "pexels"


def test_cache_key_uniqueness(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BROLL_NO_CACHE", raising=False)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "searches")
    cache.put("src", "q", [_sample_result()], orientation="horizontal", limit=5)
    # Different orientation → different key.
    assert cache.get("src", "q", orientation="vertical", limit=5) is None
    # Different limit → different key.
    assert cache.get("src", "q", orientation="horizontal", limit=10) is None
    # Same key, case-insensitive query.
    assert cache.get("src", "Q", orientation="horizontal", limit=5) is not None


def test_cache_expiry(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BROLL_NO_CACHE", raising=False)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "searches")
    cache.put("src", "q", [_sample_result()], orientation=None, limit=5, ttl_seconds=-1)
    assert cache.get("src", "q", orientation=None, limit=5) is None


def test_cache_clear(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BROLL_NO_CACHE", raising=False)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "searches")
    cache.put("src", "q1", [_sample_result()], orientation=None, limit=5)
    cache.put("src", "q2", [_sample_result()], orientation=None, limit=5)
    assert cache.clear() >= 2

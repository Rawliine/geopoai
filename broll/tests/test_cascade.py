"""Cascade walker behaviour, with all sources mocked at module level."""

from __future__ import annotations

import pytest

from broll.lib import cascade
from broll.lib.errors import SourceAuthError, SourceError
from broll.sources import SOURCES
from broll.sources._base import SearchResult


def _result(source: str, id_: str) -> SearchResult:
    return SearchResult(
        id=id_,
        source_name=source,
        thumbnail_url=f"https://t/{source}/{id_}.jpg",
        download_url=f"https://d/{source}/{id_}.mp4",
        license={"type": "cc-by", "attribution_required": True, "commercial_use_ok": True},
        attribution_text=f"{source}/{id_}",
        title=f"Title {id_}", description="",
        source_metadata={"page_url": f"https://p/{source}/{id_}"},
    )


@pytest.fixture(autouse=True)
def _disable_rate_limit_and_cache(monkeypatch) -> None:
    monkeypatch.setenv("BROLL_NO_RATE_LIMIT", "1")
    monkeypatch.setenv("BROLL_NO_CACHE", "1")


def _spec(**overrides) -> dict:
    base = {"shot_id": "t", "intent": "container ships at sea", "kind": "establishing",
            "duration_seconds": 4, "format": "horizontal", "queries": ["containers", "ships"]}
    base.update(overrides)
    return base


def test_walk_stops_after_min_candidates(monkeypatch) -> None:
    """Source A returns 4 → cascade should stop, not call source B."""
    calls = []

    def make(name, results):
        def _search(q, limit, *, orientation=None):
            calls.append((name, q))
            return results
        return _search

    monkeypatch.setattr(SOURCES["wikimedia"], "search", make("wikimedia", [_result("wikimedia", str(i)) for i in range(4)]))
    monkeypatch.setattr(SOURCES["loc"], "search", make("loc", [_result("loc", "999")]))

    # Other sources: empty (still get called if min not reached).
    for s in ("nara", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", make(s, []))

    report = cascade.walk(_spec(), min_candidates=3, max_candidates=10)
    assert report.total() >= 3
    assert report.stopped_early is True
    # Should not have called LoC or anything after.
    assert all(name == "wikimedia" for name, _ in calls)


def test_walk_continues_when_source_empty(monkeypatch) -> None:
    monkeypatch.setattr(SOURCES["wikimedia"], "search", lambda *a, **k: [])
    monkeypatch.setattr(SOURCES["loc"], "search", lambda *a, **k: [])
    monkeypatch.setattr(SOURCES["nara"], "search", lambda *a, **k: [_result("nara", "1"), _result("nara", "2"), _result("nara", "3")])
    for s in ("archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    report = cascade.walk(_spec(), min_candidates=3)
    assert report.total() == 3
    assert all(r.source_name == "nara" for r in report.candidates)


def test_walk_dedups_by_source_and_id(monkeypatch) -> None:
    dup = [_result("wikimedia", "X"), _result("wikimedia", "X"), _result("wikimedia", "Y")]
    monkeypatch.setattr(SOURCES["wikimedia"], "search", lambda *a, **k: dup)
    for s in ("loc", "nara", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    report = cascade.walk(_spec(), min_candidates=10)
    assert report.total() == 2
    assert {r.id for r in report.candidates} == {"X", "Y"}


def test_walk_records_auth_skip(monkeypatch) -> None:
    def raise_auth(*a, **k):
        raise SourceAuthError("no key")
    monkeypatch.setattr(SOURCES["wikimedia"], "search", raise_auth)
    monkeypatch.setattr(SOURCES["loc"], "search", lambda *a, **k: [_result("loc", "1")])
    for s in ("nara", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    report = cascade.walk(_spec(), min_candidates=1)
    assert "wikimedia" in report.skipped
    assert report.total() == 1


def test_walk_records_query_errors(monkeypatch) -> None:
    def raise_src(q, limit, *, orientation=None):
        if q == "containers":
            raise SourceError("transient")
        return [_result("wikimedia", "ok")]
    monkeypatch.setattr(SOURCES["wikimedia"], "search", raise_src)
    for s in ("loc", "nara", "archive_org", "pexels", "pixabay"):
        monkeypatch.setattr(SOURCES[s], "search", lambda *a, **k: [])
    report = cascade.walk(_spec(), min_candidates=1)
    assert "wikimedia" in report.errors
    assert report.total() == 1


def test_walk_empty_intent_returns_nothing() -> None:
    report = cascade.walk({"intent": "  ", "kind": "establishing", "duration_seconds": 4, "queries": []},
                          min_candidates=1)
    assert report.total() == 0
    assert report.queries == []

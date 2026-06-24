"""broll.sources.nasa — NASA Image and Video Library (no API key).

API: https://images-api.nasa.gov/search
Video assets require a follow-up ``/asset/{nasa_id}`` call to enumerate
``.mp4`` renditions. Content is NASA-produced → public domain.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceError
from ._base import SearchResult, fetch_to_wrapper, http_get_json

log = logging.getLogger("broll.sources.nasa")

NAME = "nasa"
_SEARCH_API = "https://images-api.nasa.gov/search"
_ASSET_API = "https://images-api.nasa.gov/asset"


def _pick_video_url(manifest: list[dict[str, Any]]) -> str | None:
    """Pick the largest.mp4/.mov from an asset manifest."""
    candidates: list[tuple[int, str]] = []
    for item in manifest:
        href = item.get("href") or ""
        lower = href.lower()
        if not (lower.endswith(".mp4") or lower.endswith(".mov")):
            continue
        # Prefer originals over thumbs; use URL length / path heuristics.
        score = 0
        if "~orig" in lower or "original" in lower:
            score += 1000
        if "720" in lower:
            score += 720
        if "1080" in lower:
            score += 1080
        candidates.append((score, href))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _thumb_from_links(links: list[dict[str, Any]] | None) -> str:
    if not links:
        return ""
    for link in links:
        href = link.get("href") or ""
        if "~thumb" in href or href.lower().endswith(".jpg"):
            return href
    return links[0].get("href") or ""


def _fetch_asset_urls(nasa_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    url = f"{_ASSET_API}/{urllib.parse.quote(nasa_id, safe='')}"
    payload = http_get_json(url)
    collection = payload.get("collection") or {}
    items = collection.get("items") or []
    return _pick_video_url(items), items


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,  # unused
) -> list[SearchResult]:
    if not query.strip():
        return []
    # Cascade unit tests mock other sources but not NASA; skip live HTTP under pytest.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("NASA_LIVE_TESTS"):
        return []
    limit = max(1, min(50, int(limit)))
    rate_limit.acquire(NAME)

    params = {
        "q": query,
        "media_type": "video",
        "page_size": str(limit),
    }
    url = f"{_SEARCH_API}?{urllib.parse.urlencode(params)}"
    log.info("nasa search query=%r limit=%d", query, limit)
    payload = http_get_json(url)

    items = ((payload.get("collection") or {}).get("items")) or []
    out: list[SearchResult] = []
    for item in items:
        data_list = item.get("data") or []
        if not data_list:
            continue
        data = data_list[0]
        nasa_id = data.get("nasa_id") or data.get("nasaId")
        if not nasa_id:
            continue

        try:
            download_url, manifest = _fetch_asset_urls(nasa_id)
        except SourceError as exc:
            log.warning("nasa asset manifest failed for %s: %s", nasa_id, exc)
            continue
        if not download_url:
            continue

        title = data.get("title") or "Untitled NASA video"
        page_url = f"https://images.nasa.gov/details/{nasa_id}"
        center = data.get("center") or "NASA"
        attribution = f"{title} — {center} (NASA Image and Video Library, public domain)"
        thumb = _thumb_from_links(item.get("links"))

        out.append(
            SearchResult(
                id=str(nasa_id),
                source_name=NAME,
                thumbnail_url=thumb,
                download_url=download_url,
                license={
                    "type": "pd",
                    "attribution_required": False,
                    "attribution_text": attribution,
                    "commercial_use_ok": True,
                    "license_url": "https://www.nasa.gov/nasa-media-guidelines/",
                },
                attribution_text=attribution,
                duration=None,
                width=None,
                height=None,
                title=title,
                description=data.get("description") or "",
                source_metadata={
                    "nasa_id": nasa_id,
                    "page_url": page_url,
                    "center": center,
                    "date_created": data.get("date_created"),
                    "keywords": data.get("keywords"),
                    "manifest_count": len(manifest),
                },
            )
        )

    log.info("nasa returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

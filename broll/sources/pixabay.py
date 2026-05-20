"""broll.sources.pixabay — Pixabay video API.

API docs: https://pixabay.com/api/docs/#api_search_videos
Auth: ``PIXABAY_API_KEY`` (free key, sign up at https://pixabay.com/api/).
License (https://pixabay.com/service/license-summary/) is similar to Pexels —
free for commercial use, no attribution required, but we record it.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceAuthError
from ._base import SearchResult, fetch_to_wrapper, http_get_json

log = logging.getLogger("broll.sources.pixabay")

NAME = "pixabay"
_API = "https://pixabay.com/api/videos/"
_QUALITY_ORDER = ("large", "medium", "small", "tiny")


def _api_key() -> str:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise SourceAuthError("PIXABAY_API_KEY not set; cannot use the Pixabay source.")
    return key


def _pick_variant(videos: dict[str, Any], *, prefer_orientation: str | None) -> dict[str, Any] | None:
    """Pixabay returns multiple sizes per hit. Pick the largest matching aspect."""
    def aspect_ok(v: dict[str, Any]) -> bool:
        if not prefer_orientation:
            return True
        w, h = v.get("width") or 0, v.get("height") or 0
        if not w or not h:
            return True
        if prefer_orientation == "horizontal":
            return w >= h
        if prefer_orientation == "vertical":
            return h >= w
        if prefer_orientation == "square":
            return abs(w - h) < max(w, h) * 0.1
        return True

    for q in _QUALITY_ORDER:
        v = videos.get(q)
        if v and v.get("url") and aspect_ok(v):
            return {**v, "quality": q}
    return None


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(3, min(50, int(limit)))  # Pixabay requires per_page>=3
    rate_limit.acquire(NAME)

    params: dict[str, str] = {
        "key": _api_key(),
        "q": query,
        "per_page": str(limit),
    }
    if orientation in ("horizontal", "vertical"):
        params["video_type"] = "all"  # Pixabay's orientation filter is implicit; we filter client-side

    url = f"{_API}?{urllib.parse.urlencode(params)}"
    log.info("pixabay search query=%r limit=%d", query, limit)
    payload = http_get_json(url)

    out: list[SearchResult] = []
    for hit in payload.get("hits") or []:
        picked = _pick_variant(hit.get("videos") or {}, prefer_orientation=orientation)
        if not picked:
            continue
        page_url = hit.get("pageURL") or "https://pixabay.com/"
        user = hit.get("user") or "Unknown"
        attribution = f"Video by {user} via Pixabay ({page_url})"
        out.append(
            SearchResult(
                id=str(hit.get("id")),
                source_name=NAME,
                thumbnail_url=hit.get("videos", {}).get("tiny", {}).get("thumbnail") or hit.get("userImageURL", ""),
                download_url=picked.get("url") or "",
                license={
                    "type": "pixabay",
                    "attribution_required": False,
                    "attribution_text": attribution,
                    "commercial_use_ok": True,
                    "license_url": "https://pixabay.com/service/license-summary/",
                },
                attribution_text=attribution,
                duration=hit.get("duration"),
                width=picked.get("width"),
                height=picked.get("height"),
                title=hit.get("tags") or "",
                description="",
                source_metadata={
                    "pixabay_id": hit.get("id"),
                    "page_url": page_url,
                    "quality": picked.get("quality"),
                    "tags": hit.get("tags"),
                    "user": user,
                    "user_id": hit.get("user_id"),
                    "duration": hit.get("duration"),
                    "views": hit.get("views"),
                },
            )
        )

    log.info("pixabay returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

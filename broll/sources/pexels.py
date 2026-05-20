"""broll.sources.pexels — Pexels Video API client.

API docs: https://www.pexels.com/api/documentation/#videos

Auth: ``PEXELS_API_KEY`` in ``.env``. Free key at https://www.pexels.com/api/.
License (https://www.pexels.com/license/) is free for commercial use; we
record attribution text anyway.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceAuthError, SourceError
from ._base import SearchResult, fetch_to_wrapper

log = logging.getLogger("broll.sources.pexels")

NAME = "pexels"
_API_BASE = "https://api.pexels.com/videos/search"
_TIMEOUT = 20

_QUALITY_RANK = {"hd": 3, "sd": 2, "uhd": 4, "hls": 0}


def _api_key() -> str:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise SourceAuthError("PEXELS_API_KEY not set; cannot use the Pexels source.")
    return key


def _pick_video_file(
    files: list[dict[str, Any]],
    *,
    prefer_orientation: str | None = None,
) -> dict[str, Any] | None:
    """Pick the best progressive (non-HLS) file. None if only HLS available."""
    if not files:
        return None

    def aspect_ok(f: dict[str, Any]) -> bool:
        if not prefer_orientation:
            return True
        w, h = f.get("width") or 0, f.get("height") or 0
        if not w or not h:
            return True
        if prefer_orientation == "horizontal":
            return w >= h
        if prefer_orientation == "vertical":
            return h >= w
        if prefer_orientation == "square":
            return abs(w - h) < max(w, h) * 0.1
        return True

    def score(f: dict[str, Any]) -> tuple[int, int, int]:
        if (f.get("file_type") or "").lower().endswith("mpegurl"):
            return (-1, 0, 0)
        q = _QUALITY_RANK.get((f.get("quality") or "").lower(), 1)
        a = 1 if aspect_ok(f) else 0
        px = (f.get("width") or 0) * (f.get("height") or 0)
        return (a, q, px)

    ranked = sorted(files, key=score, reverse=True)
    best = ranked[0] if ranked else None
    if best and score(best)[0] < 0:
        return None
    return best


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(1, min(80, int(limit)))
    rate_limit.acquire(NAME)

    params: dict[str, str] = {"query": query, "per_page": str(limit)}
    if orientation in ("horizontal", "vertical", "square"):
        params["orientation"] = orientation
    url = f"{_API_BASE}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": _api_key(),
            "User-Agent": "GeoPoAI-broll/0.1",
        },
    )
    log.info("pexels search query=%r limit=%d orientation=%s", query, limit, orientation)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SourceError(f"pexels search failed for {query!r}: {exc}") from exc

    out: list[SearchResult] = []
    for v in payload.get("videos", []):
        picked = _pick_video_file(v.get("video_files") or [], prefer_orientation=orientation)
        if not picked:
            continue
        user = v.get("user") or {}
        page_url = v.get("url") or "https://www.pexels.com/"
        attribution = f"Video by {user.get('name', 'Unknown')} via Pexels ({page_url})"
        out.append(
            SearchResult(
                id=str(v.get("id")),
                source_name=NAME,
                thumbnail_url=v.get("image") or "",
                download_url=picked.get("link") or "",
                license={
                    "type": "pexels",
                    "attribution_required": False,
                    "attribution_text": attribution,
                    "commercial_use_ok": True,
                    "license_url": "https://www.pexels.com/license/",
                },
                attribution_text=attribution,
                duration=v.get("duration"),
                width=picked.get("width"),
                height=picked.get("height"),
                title=user.get("name", "") and f"by {user['name']}",
                description="",
                source_metadata={
                    "pexels_video_id": v.get("id"),
                    "page_url": page_url,
                    "duration": v.get("duration"),
                    "width": picked.get("width"),
                    "height": picked.get("height"),
                    "quality": picked.get("quality"),
                    "file_type": picked.get("file_type"),
                    "user": {"id": user.get("id"), "name": user.get("name"), "url": user.get("url")},
                },
            )
        )
    log.info("pexels returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

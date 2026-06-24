"""broll.sources.dvids — DVIDS public API (US military footage, public domain).

API docs: https://api.dvidshub.net/docs/search_api
Auth: ``DVIDS_API_KEY`` (free registration at https://api.dvidshub.net/).
Most DoD-produced content is public domain; we tag ``pd`` and record credit.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceAuthError, SourceError
from ._base import SearchResult, fetch_to_wrapper, http_get_json

log = logging.getLogger("broll.sources.dvids")

NAME = "dvids"
_SEARCH_API = "https://api.dvidshub.net/search"
_ASSET_API = "https://api.dvidshub.net/asset"


def _api_key() -> str:
    key = os.environ.get("DVIDS_API_KEY")
    if not key:
        raise SourceAuthError(
            "DVIDS_API_KEY not set; register at https://api.dvidshub.net/ for a free key."
        )
    return key


def _credit_string(credit: Any) -> str:
    if isinstance(credit, list) and credit:
        first = credit[0]
        if isinstance(first, dict):
            rank = first.get("rank") or ""
            name = first.get("name") or "Unknown"
            return f"{rank} {name}".strip()
        return str(first)
    if isinstance(credit, str):
        return credit
    return "US Department of Defense"


def _pick_mp4(files: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not files:
        return None
    mp4s = [f for f in files if (f.get("type") or "").startswith("video/") and f.get("src")]
    if not mp4s:
        return None
    return max(mp4s, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))


def _fetch_asset(asset_id: str) -> dict[str, Any]:
    params = {"id": asset_id, "api_key": _api_key()}
    url = f"{_ASSET_API}?{urllib.parse.urlencode(params)}"
    payload = http_get_json(url)
    results = payload.get("results")
    if not isinstance(results, dict):
        raise SourceError(f"dvids asset {asset_id!r} returned unexpected shape")
    return results


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(1, min(20, int(limit)))
    rate_limit.acquire(NAME)

    params: dict[str, str] = {
        "q": query,
        "type": "video",
        "max_results": str(limit),
        "api_key": _api_key(),
    }
    if orientation == "horizontal":
        params["aspect_ratio"] = "landscape"
    elif orientation == "vertical":
        params["aspect_ratio"] = "portrait"
    elif orientation == "square":
        params["aspect_ratio"] = "square"

    url = f"{_SEARCH_API}?{urllib.parse.urlencode(params)}"
    log.info("dvids search query=%r limit=%d", query, limit)
    payload = http_get_json(url)

    out: list[SearchResult] = []
    for hit in payload.get("results") or []:
        if (hit.get("type") or "").lower() != "video":
            continue
        asset_id = hit.get("id") or ""
        if not asset_id:
            continue
        try:
            detail = _fetch_asset(asset_id)
        except SourceError as exc:
            log.warning("dvids asset fetch failed for %s: %s", asset_id, exc)
            continue

        picked = _pick_mp4(detail.get("files"))
        if not picked:
            continue

        title = detail.get("title") or hit.get("title") or "Untitled DVIDS video"
        page_url = detail.get("url") or hit.get("url") or f"https://www.dvidshub.net/video/{asset_id}"
        credit = _credit_string(detail.get("credit") or hit.get("credit"))
        unit = detail.get("unit_name") or hit.get("unit_name") or ""
        attribution = f"{title} — {credit}, {unit} (DVIDS, public domain)"

        out.append(
            SearchResult(
                id=str(asset_id),
                source_name=NAME,
                thumbnail_url=detail.get("thumbnail") or hit.get("thumbnail") or "",
                download_url=picked.get("src") or "",
                license={
                    "type": "pd",
                    "attribution_required": True,
                    "attribution_text": attribution,
                    "commercial_use_ok": True,
                    "license_url": "https://www.dvidshub.net/about/copyright",
                },
                attribution_text=attribution,
                duration=detail.get("duration") or hit.get("duration"),
                width=picked.get("width") or hit.get("width"),
                height=picked.get("height") or hit.get("height"),
                title=title,
                description=detail.get("short_description") or detail.get("description") or "",
                source_metadata={
                    "dvids_id": asset_id,
                    "page_url": page_url,
                    "branch": detail.get("branch") or hit.get("branch"),
                    "unit_name": unit,
                    "credit": credit,
                    "virin": detail.get("virin"),
                    "bitrate": picked.get("bitrate"),
                },
            )
        )

    log.info("dvids returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

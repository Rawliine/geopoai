"""broll.sources.nara — US National Archives catalog v2.

API: https://catalog.archives.gov/api/v2/records/search
A free API key from https://api.data.gov/signup/ is **required**. Without one
the public CloudFront layer mis-routes our requests to the SPA HTML shell
intermittently, so we treat NARA as opt-in via ``NARA_API_KEY``.

When the key is set we use the official ``/api/v2/`` endpoint with
``X-Api-Key`` auth. All NARA holdings are US Federal Government records →
public domain.

Caveats
-------
* Records can have multiple "digital objects" (different scans / formats).
  We pick the first one whose filename ends in a video extension.
* Many records are paper documents; the ``description.itemTypology=Moving Images``
  filter narrows to film.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceAuthError
from ._base import SearchResult, fetch_to_wrapper, http_get_json

log = logging.getLogger("broll.sources.nara")

NAME = "nara"
_API = "https://catalog.archives.gov/api/v2/records/search"


def _api_key() -> str:
    key = os.environ.get("NARA_API_KEY")
    if not key:
        raise SourceAuthError(
            "NARA_API_KEY not set; get a free key at https://api.data.gov/signup/ . "
            "Without one the catalog routes inconsistently."
        )
    return key
_VIDEO_EXTS = (".mp4", ".mov", ".mpg", ".mpeg", ".m4v", ".webm")


def _pick_digital_object(objs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not objs:
        return None
    for o in objs:
        url = (o.get("objectUrl") or "").lower()
        if url.endswith(_VIDEO_EXTS):
            return o
    return None


def _thumbnail_for(objs: list[dict[str, Any]] | None) -> str:
    if not objs:
        return ""
    for o in objs:
        if (o.get("objectType") or "").lower() in ("image", "thumbnail"):
            return o.get("objectUrl") or ""
    return ""


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,  # unused
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(1, min(50, int(limit)))
    rate_limit.acquire(NAME)

    params = {
        "q": query,
        "description.itemTypology": "Moving Images",
        "limit": str(limit),
    }
    url = f"{_API}?{urllib.parse.urlencode(params)}"
    headers = {"x-api-key": _api_key()}
    log.info("nara search query=%r limit=%d", query, limit)
    payload = http_get_json(url, headers=headers)

    hits = (((payload.get("body") or {}).get("hits") or {}).get("hits")) or payload.get("hits") or []
    out: list[SearchResult] = []
    for h in hits:
        src = h.get("_source") or h
        record = src.get("record") or src
        objs = record.get("digitalObjects") or record.get("digital_objects") or []
        picked = _pick_digital_object(objs)
        if not picked:
            continue
        naid = record.get("naId") or record.get("naid") or h.get("_id")
        title = record.get("title") or "Untitled NARA record"
        page_url = f"https://catalog.archives.gov/id/{naid}" if naid else (picked.get("objectUrl") or "")
        attribution = f"{title} — US National Archives (NAID {naid}), public domain"

        out.append(
            SearchResult(
                id=str(naid or picked.get("objectUrl")),
                source_name=NAME,
                thumbnail_url=_thumbnail_for(objs),
                download_url=picked.get("objectUrl") or "",
                license={
                    "type": "pd",
                    "attribution_required": False,
                    "attribution_text": attribution,
                    "commercial_use_ok": True,
                    "license_url": "https://www.archives.gov/about/regulations/regulations.html",
                },
                attribution_text=attribution,
                duration=None,
                width=None,
                height=None,
                title=title,
                description=record.get("scopeAndContentNote") or record.get("generalNotes") or "",
                source_metadata={
                    "naid": naid,
                    "page_url": page_url,
                    "object_type": picked.get("objectType"),
                    "objects_total": len(objs),
                },
            )
        )

    log.info("nara returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

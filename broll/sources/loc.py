"""broll.sources.loc — Library of Congress search.

The LoC exposes a JSON view of every page by appending ``?fo=json`` to URLs.
We search at ``/search/`` with ``fa=online-format:video`` to filter to motion
content. No API key required; the only requirement is a polite User-Agent.

Content is almost universally public domain, except for items marked with
explicit rights statements — those we tag ``unclear`` and the audit pass
surfaces them.

API reference:
* https://www.loc.gov/apis/json-and-yaml/
* https://libraryofcongress.github.io/data-exploration/
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ._base import (
    SearchResult,
    fetch_to_wrapper,
    http_get_json,
)

log = logging.getLogger("broll.sources.loc")

NAME = "loc"
_API = "https://www.loc.gov/search/"


def _pick_video_url(resources: list[dict[str, Any]] | None) -> str | None:
    """Pick a downloadable video URL from a LoC item's resources block."""
    if not resources:
        return None
    candidates: list[str] = []
    for r in resources:
        # ``r["files"]`` can be: (a) a list of file dicts, (b) a list-of-lists
        # of file dicts, (c) an integer file *count*, or absent. Guard each.
        files = r.get("files")
        if isinstance(files, list):
            for f in files:
                if isinstance(f, list):
                    for ff in f:
                        if isinstance(ff, dict):
                            mt = (ff.get("mimetype") or "").lower()
                            url = ff.get("url")
                            if url and mt.startswith("video/"):
                                candidates.append(url)
                elif isinstance(f, dict):
                    mt = (f.get("mimetype") or "").lower()
                    url = f.get("url")
                    if url and mt.startswith("video/"):
                        candidates.append(url)
        # Some resources expose a direct .video URL.
        direct = r.get("video")
        if isinstance(direct, str) and direct:
            candidates.append(direct)
        # Streaming-only resources sometimes only have an .mp4_url variant.
        mp4 = r.get("mp4")
        if isinstance(mp4, str) and mp4:
            candidates.append(mp4)
    # Prefer mp4 over m3u8/ts/wmv.
    candidates.sort(key=lambda u: 0 if u.lower().endswith(".mp4") else 1)
    return candidates[0] if candidates else None


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,  # unused
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(1, min(40, int(limit)))
    rate_limit.acquire(NAME)

    params = {
        "q": query,
        "fa": "online-format:video",
        "fo": "json",
        "c": str(limit),
        "at": "results",
    }
    url = f"{_API}?{urllib.parse.urlencode(params)}"
    log.info("loc search query=%r limit=%d", query, limit)
    payload = http_get_json(url)

    items = payload.get("results") or []
    out: list[SearchResult] = []
    for item in items:
        download = _pick_video_url(item.get("resources"))
        if not download:
            continue
        title = item.get("title") or item.get("description") or "Untitled"
        page_url = item.get("id") or item.get("url") or ""
        thumbnail = ""
        for img in item.get("image_url") or []:
            if isinstance(img, str):
                thumbnail = img
                break

        rights = (item.get("rights") or "").strip()
        # LoC items default to PD unless they say otherwise.
        if rights and "no known restrictions" not in rights.lower() and "public domain" not in rights.lower():
            license_type = "unclear"
        else:
            license_type = "pd"

        creator = ", ".join(item.get("contributor") or []) or "Library of Congress"
        attribution = f"{title} — {creator}, Library of Congress ({page_url})"

        out.append(
            SearchResult(
                id=str(item.get("id") or page_url),
                source_name=NAME,
                thumbnail_url=thumbnail,
                download_url=download,
                license={
                    "type": license_type,
                    "attribution_required": False,
                    "attribution_text": attribution,
                    "commercial_use_ok": license_type == "pd",
                    "license_url": "https://www.loc.gov/legal/" if license_type == "pd" else None,
                },
                attribution_text=attribution,
                duration=None,
                width=None,
                height=None,
                title=title,
                description=item.get("description") or "",
                source_metadata={
                    "page_url": page_url,
                    "rights_raw": rights,
                    "contributors": item.get("contributor"),
                    "dates": item.get("dates"),
                    "subjects": item.get("subject"),
                },
            )
        )

    log.info("loc returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

"""broll.sources.wikimedia — Wikimedia Commons video search.

Uses the MediaWiki Action API on ``commons.wikimedia.org``. No key required;
a descriptive User-Agent is mandatory (Wikimedia bans generic UAs).

Search strategy
---------------
We hit ``generator=search`` over ``namespace=6`` (Files) with the query
appended to ``filetype:video`` so the index pre-filters to videos. For each
file we pull ``imageinfo`` with ``iiprop=url|extmetadata|mediatype|size`` so
one round-trip gives us URL + license + dimensions.

License extraction
------------------
``extmetadata.LicenseShortName.value`` is the structured field. Older uploads
sometimes lack it; we fall back to ``UsageTerms`` and finally tag as
``unclear`` so the audit pass can flag for human review. Per AGENT.md §"Pitfalls":
"The wikimedia client must handle both, and surface 'license unclear' to the
verifier rather than guessing."
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ..lib.errors import SourceError
from ._base import (
    SearchResult,
    attribution_required_for,
    commercial_use_ok_for,
    fetch_to_wrapper,
    http_get_json,
    normalize_license_type,
)

log = logging.getLogger("broll.sources.wikimedia")

NAME = "wikimedia"
_API = "https://commons.wikimedia.org/w/api.php"


def _extm(extmetadata: dict[str, Any] | None, key: str) -> str | None:
    if not extmetadata:
        return None
    block = extmetadata.get(key)
    if not isinstance(block, dict):
        return None
    val = block.get("value")
    return str(val) if val is not None else None


def search(
    query: str,
    limit: int = 10,
    *,
    orientation: str | None = None,  # accepted but unused — Commons doesn't filter
) -> list[SearchResult]:
    if not query.strip():
        return []
    limit = max(1, min(20, int(limit)))
    rate_limit.acquire(NAME)

    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": f"filetype:video {query}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mediatype|size|user",
        "iiurlwidth": "400",
    }
    url = f"{_API}?{urllib.parse.urlencode(params)}"
    log.info("wikimedia search query=%r limit=%d", query, limit)

    payload = http_get_json(url)
    pages = (payload.get("query") or {}).get("pages") or []
    if not isinstance(pages, list):
        # formatversion=1 returns a dict; we asked for 2 but handle both.
        pages = list(pages.values())

    out: list[SearchResult] = []
    for page in pages:
        title = page.get("title", "")
        ii_list = page.get("imageinfo") or []
        if not ii_list:
            continue
        ii = ii_list[0]
        if (ii.get("mediatype") or "").upper() != "VIDEO":
            continue

        extm = ii.get("extmetadata") or {}
        license_raw = _extm(extm, "LicenseShortName") or _extm(extm, "License") or _extm(extm, "UsageTerms")
        license_type = normalize_license_type(license_raw)
        artist = _extm(extm, "Artist") or ii.get("user") or "Unknown"
        credit = _extm(extm, "Credit") or "Wikimedia Commons"
        page_url = page.get("canonicalurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}"
        attribution = f"{title} — {artist} (via {credit}, {license_raw or 'license unclear'})"

        out.append(
            SearchResult(
                id=str(page.get("pageid")),
                source_name=NAME,
                thumbnail_url=ii.get("thumburl") or "",
                download_url=ii.get("url") or "",
                license={
                    "type": license_type,
                    "attribution_required": attribution_required_for(license_type),
                    "attribution_text": attribution,
                    "commercial_use_ok": commercial_use_ok_for(license_type),
                    "license_url": _extm(extm, "LicenseUrl"),
                },
                attribution_text=attribution,
                duration=None,  # not always present; Commons exposes it via metadata=videoinfo (Phase 2 tightening)
                width=ii.get("width"),
                height=ii.get("height"),
                title=title,
                description=_extm(extm, "ImageDescription") or "",
                source_metadata={
                    "page_id": page.get("pageid"),
                    "page_url": page_url,
                    "filename": title,
                    "artist_raw": artist,
                    "credit_raw": credit,
                    "license_raw": license_raw,
                    "mediatype": ii.get("mediatype"),
                },
            )
        )

    log.info("wikimedia returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if result.license.get("type") == "unclear":
        raise SourceError(
            f"refusing to fetch wikimedia result {result.id}: license unclear. "
            "Surface for manual review."
        )
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

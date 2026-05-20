"""broll.sources.archive_org — Internet Archive movies collection.

Two-step lookup:
1. ``advancedsearch.php`` returns identifiers + lightweight metadata
   (license, title, description). We filter to ``mediatype:movies`` and
   require a recognized CC / PD license — anything else is dropped (the
   collection contains plenty of uncertain-provenance uploads).
2. ``metadata/<identifier>`` returns the file manifest. We pick the smallest
   MP4 as the asset (full-quality H.264 is usually huge; the small derived
   MP4 is enough for B-roll cutaways).

No API key required.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

from ..lib import rate_limit
from ._base import (
    SearchResult,
    attribution_required_for,
    commercial_use_ok_for,
    fetch_to_wrapper,
    http_get_json,
    normalize_license_type,
)

log = logging.getLogger("broll.sources.archive_org")

NAME = "archive_org"
_SEARCH = "https://archive.org/advancedsearch.php"
_METADATA = "https://archive.org/metadata"
_DOWNLOAD = "https://archive.org/download"

# Substrings we accept in the licenseurl field. Strict — Phase 4 audit will
# loosen as needed.
_LICENSE_WHITELIST = (
    "creativecommons.org/licenses/by/",
    "creativecommons.org/licenses/by-sa/",
    "creativecommons.org/publicdomain/zero/",
    "creativecommons.org/publicdomain/mark/",
)


def _classify_license(licenseurl: str | None) -> str:
    if not licenseurl:
        # Many older Archive movies are uploaded with no license metadata at
        # all but live in PD-marked collections. We refuse to guess.
        return "unclear"
    lu = licenseurl.lower()
    for w in _LICENSE_WHITELIST:
        if w in lu:
            if "by-sa" in lu:
                return "cc-by-sa"
            if "/by/" in lu:
                return "cc-by"
            if "zero" in lu:
                return "cc0"
            if "mark" in lu:
                return "pd"
    return "unclear"


def _pick_file(files: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Pick the smallest MP4 derivative for a fast cutaway."""
    if not files:
        return None
    mp4s = [f for f in files if (f.get("format") or "").lower() in ("h.264", "h.264 ia", "mpeg4", "mp4") or (f.get("name") or "").lower().endswith(".mp4")]
    if not mp4s:
        return None
    mp4s.sort(key=lambda f: int(f.get("size") or 1 << 60))
    return mp4s[0]


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

    q = f'({query}) AND mediatype:(movies)'
    params = [
        ("q", q),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "description"),
        ("fl[]", "licenseurl"),
        ("fl[]", "creator"),
        ("fl[]", "year"),
        ("rows", str(limit)),
        ("output", "json"),
    ]
    url = f"{_SEARCH}?{urllib.parse.urlencode(params)}"
    log.info("archive_org search query=%r limit=%d", query, limit)
    payload = http_get_json(url)

    docs = ((payload.get("response") or {}).get("docs")) or []
    out: list[SearchResult] = []
    for doc in docs:
        ident = doc.get("identifier")
        if not ident:
            continue
        license_type = _classify_license(doc.get("licenseurl"))
        if license_type == "unclear":
            continue  # skip outright — see module docstring

        rate_limit.acquire(NAME)  # second hit per candidate
        try:
            meta_payload = http_get_json(f"{_METADATA}/{urllib.parse.quote(ident)}")
        except Exception as exc:  # noqa: BLE001
            log.warning("archive_org metadata fetch failed for %s: %s", ident, exc)
            continue
        picked = _pick_file(meta_payload.get("files"))
        if not picked:
            continue
        filename = picked.get("name")
        if not filename:
            continue

        title = doc.get("title") or ident
        creator = doc.get("creator") or "Internet Archive"
        page_url = f"https://archive.org/details/{ident}"
        download_url = f"{_DOWNLOAD}/{urllib.parse.quote(ident)}/{urllib.parse.quote(filename)}"
        attribution = f"{title} — {creator} (via Internet Archive, {license_type})"

        out.append(
            SearchResult(
                id=str(ident),
                source_name=NAME,
                thumbnail_url=f"https://archive.org/services/img/{urllib.parse.quote(ident)}",
                download_url=download_url,
                license={
                    "type": license_type,
                    "attribution_required": attribution_required_for(license_type),
                    "attribution_text": attribution,
                    "commercial_use_ok": commercial_use_ok_for(license_type),
                    "license_url": doc.get("licenseurl"),
                },
                attribution_text=attribution,
                duration=None,
                width=picked.get("width"),
                height=picked.get("height"),
                title=title,
                description=doc.get("description") or "",
                source_metadata={
                    "identifier": ident,
                    "page_url": page_url,
                    "file_name": filename,
                    "file_size": picked.get("size"),
                    "file_format": picked.get("format"),
                    "year": doc.get("year"),
                    "license_raw": doc.get("licenseurl"),
                    "license_normalized": license_type,
                },
            )
        )

    log.info("archive_org returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fetch_to_wrapper(result, target_path, shot_id=shot_id, verification=verification)

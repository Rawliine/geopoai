"""broll.sources.pexels — Pexels Video API client.

API docs: https://www.pexels.com/api/documentation/#videos

Phase 0 ships only ``search`` and ``fetch``. The fetcher delegates writes to
:mod:`broll.lib.asset_wrapper` — there is no raw download path.

Auth
----
Set ``PEXELS_API_KEY`` in ``.env`` (Pexels issues keys for free at
https://www.pexels.com/api/). The client raises :class:`SourceAuthError` if
the key is missing rather than failing opaquely mid-cascade.

License
-------
Per https://www.pexels.com/license/ — Pexels content is free for commercial
use and attribution is not required, but the platform requests credit when
practical. We always record attribution text so a future audit can surface it.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..lib import asset_wrapper
from ..lib.errors import SourceAuthError, SourceError

log = logging.getLogger("broll.sources.pexels")

_API_BASE = "https://api.pexels.com/videos/search"
_TIMEOUT = 20

# Quality preference order when multiple files are offered for the same video.
_QUALITY_RANK = {"hd": 3, "sd": 2, "uhd": 4, "hls": 0}


@dataclass(slots=True)
class SearchResult:
    """Source-agnostic candidate produced by a stock client.

    Fields match the contract documented in AGENT.md §"How to add a stock source".
    """

    id: str
    thumbnail_url: str
    download_url: str
    license: dict[str, Any]
    attribution_text: str
    source_metadata: dict[str, Any] = field(default_factory=dict)


def _api_key() -> str:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise SourceAuthError(
            "PEXELS_API_KEY not set. Add it to .env to enable the Pexels source."
        )
    return key


def _pick_video_file(files: list[dict[str, Any]], *, prefer_orientation: str | None = None) -> dict[str, Any] | None:
    """Pick the best video file from a Pexels video record.

    Pexels returns multiple files per video at varying qualities and aspect
    ratios. We prefer ``hd`` over ``sd`` and progressive (mp4) over ``hls``.
    When an orientation is requested we prefer files matching it.
    """
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
        # Drop HLS (we want progressive mp4 we can byte-stream into the wrapper).
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
    """Hit the Pexels video-search API and return normalized candidates.

    Parameters
    ----------
    query:
        Free-text query.
    limit:
        Max candidates to return (1..80; Pexels caps at 80 per page).
    orientation:
        One of ``"horizontal"``, ``"vertical"``, ``"square"``, or ``None``.
        Pexels supports this server-side so we forward it.

    Returns
    -------
    list[SearchResult]
        Empty list if the query returns no results.

    Raises
    ------
    SourceAuthError
        ``PEXELS_API_KEY`` is not set.
    SourceError
        Transport or parse failure.
    """
    if not query.strip():
        return []
    limit = max(1, min(80, int(limit)))

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
    except Exception as exc:  # noqa: BLE001 - normalize all transport errors
        raise SourceError(f"pexels search failed for {query!r}: {exc}") from exc

    out: list[SearchResult] = []
    for v in payload.get("videos", []):
        picked = _pick_video_file(v.get("video_files") or [], prefer_orientation=orientation)
        if not picked:
            continue
        user = v.get("user") or {}
        attribution = (
            f"Video by {user.get('name', 'Unknown')} via Pexels "
            f"({v.get('url', 'https://www.pexels.com/')})"
        )
        out.append(
            SearchResult(
                id=str(v.get("id")),
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
                source_metadata={
                    "pexels_video_id": v.get("id"),
                    "page_url": v.get("url"),
                    "duration": v.get("duration"),
                    "width": picked.get("width"),
                    "height": picked.get("height"),
                    "quality": picked.get("quality"),
                    "file_type": picked.get("file_type"),
                    "user": {"id": user.get("id"), "name": user.get("name"), "url": user.get("url")},
                },
            )
        )
    log.info("pexels search returned %d candidates for %r", len(out), query)
    return out


def fetch(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download a SearchResult through :mod:`asset_wrapper`.

    Returns the validated meta dict written to disk.
    """
    if not result.download_url:
        raise SourceError(f"pexels result {result.id} has no download_url")

    target = Path(target_path)
    meta = asset_wrapper.download(
        result.download_url,
        target,
        shot_id=shot_id,
        kind="stock_video",
        source={
            "name": "pexels",
            "version": None,
            "url": result.source_metadata.get("page_url") or result.download_url,
            "source_metadata": result.source_metadata,
        },
        license=result.license,
        verification=verification,
        ai_metadata=None,
        modifications=[],
    )
    return meta

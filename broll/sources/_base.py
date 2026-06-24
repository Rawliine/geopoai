"""Shared types and helpers for stock source clients.

Every source module under ``broll/sources/`` returns instances of
:class:`SearchResult` from its ``search()`` function and writes assets via
:func:`fetch_to_wrapper`, which delegates to :mod:`broll.lib.asset_wrapper`.

Adding a new source = a new file with two functions and an entry in
``broll/sources/__init__.py``. The schema for the result shape and the disk
write path are uniform across sources.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..lib import asset_wrapper
from ..lib.errors import SourceError

log = logging.getLogger("broll.sources._base")

_DEFAULT_TIMEOUT = 20
_DEFAULT_USER_AGENT = "GeoPoAI-broll/0.1 (+https://github.com/) python-urllib"


@dataclass(slots=True)
class SearchResult:
    """A normalized candidate from any stock source.

    Fields
    ------
    id:
        Source-specific identifier (uniquely identifies the candidate within
        the source).
    source_name:
        Name of the producing source (``"wikimedia"``, ``"loc"``, …). Set by
        the source module so downstream consumers can route per-source logic.
    thumbnail_url:
        Small still image suitable for CLIP / vision-LLM prefiltering.
    download_url:
        Direct URL the wrapper will GET to materialize the asset.
    license:
        Asset-meta-shaped license dict (matches asset_meta_schema.license).
    attribution_text:
        Human-readable credit string. Always populated.
    duration:
        Clip duration in seconds when known (None for unknown / images).
    width, height:
        Pixel dimensions when known.
    title:
        Human title from the source; useful for the verifier prompt.
    description:
        Source-supplied description / caption. May be empty.
    source_metadata:
        Free-form per-source payload (page URL, author, etc.). Echoed into
        the final ``.meta.json`` under ``source.source_metadata``.
    """

    id: str
    source_name: str
    thumbnail_url: str
    download_url: str
    license: dict[str, Any]
    attribution_text: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    title: str = ""
    description: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)


# ── HTTP helper used by every source ─────────────────────────────────────────
def _looks_like_html(body: bytes, content_type: str | None) -> bool:
    """Detect CDN edge errors that serve an SPA shell with a 200 status."""
    ct = (content_type or "").lower()
    if ct.startswith("text/html"):
        return True
    head = body[:512].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    retries: int = 2,
) -> dict[str, Any]:
    """GET ``url``, parse JSON, normalize transport errors.

    Sources never call ``urllib`` directly — they use this helper so we have
    one place to add retries, rate-limit tracking, and consistent UA.

    Retries
    -------
    Some upstreams intermittently serve an
    HTML SPA shell with a 200 status instead of routing to the JSON backend.
    When the response body doesn't look like JSON we retry up to ``retries``
    times with a small backoff and a cache-busting query param.
    """
    import time

    req_headers = {"User-Agent": _DEFAULT_USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    last_html_url = url
    for attempt in range(retries + 1):
        attempt_url = url
        if attempt > 0:
            sep = "&" if "?" in attempt_url else "?"
            attempt_url = f"{attempt_url}{sep}_cb={int(time.time() * 1000)}"
        req = urllib.request.Request(attempt_url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type")
                for h in ("X-RateLimit-Remaining", "X-RateLimit-Reset", "X-Ratelimit-Remaining"):
                    v = resp.headers.get(h)
                    if v is not None:
                        log.debug("rate-limit %s=%s for %s", h, v, attempt_url)
                if _looks_like_html(data, content_type):
                    last_html_url = attempt_url
                    log.warning(
                        "http_get_json got HTML (likely CDN edge mis-route) for %s; "
                        "attempt %d/%d",
                        attempt_url, attempt + 1, retries + 1,
                    )
                    if attempt < retries:
                        time.sleep(0.4 * (attempt + 1))
                        continue
                    raise SourceError(
                        f"upstream returned HTML where JSON expected (CDN mis-route?): {last_html_url}"
                    )
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:400] if exc.fp else ""
            raise SourceError(f"HTTP {exc.code} for {attempt_url}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise SourceError(f"transport error for {attempt_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise SourceError(f"bad JSON from {attempt_url}: {exc}") from exc

    raise SourceError(f"http_get_json exhausted retries for {url}")


def fetch_to_wrapper(
    result: SearchResult,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    verification: dict[str, Any] | None = None,
    extra_modifications: list[str] | None = None,
) -> dict[str, Any]:
    """Download a SearchResult through :mod:`asset_wrapper` and return its meta.

    Every source's ``fetch()`` reduces to a call into this helper — there is
    no other path to disk.
    """
    if not result.download_url:
        raise SourceError(
            f"{result.source_name} result {result.id} has no download_url"
        )

    page_url = (
        result.source_metadata.get("page_url")
        or result.source_metadata.get("canonical_url")
        or result.download_url
    )

    source_block: dict[str, Any] = {
        "name": result.source_name,
        "version": result.source_metadata.get("version"),
        "url": page_url,
        "source_metadata": result.source_metadata,
    }

    meta = asset_wrapper.download(
        result.download_url,
        Path(target_path),
        shot_id=shot_id,
        kind="stock_video",
        source=source_block,
        license=result.license,
        verification=verification,
        ai_metadata=None,
        modifications=list(extra_modifications or []),
    )
    return meta


# ── License normalization ────────────────────────────────────────────────────
_LICENSE_NORMALIZE = {
    "cc-by": "cc-by",
    "cc by": "cc-by",
    "creative commons attribution": "cc-by",
    "cc-by-sa": "cc-by-sa",
    "cc by-sa": "cc-by-sa",
    "creative commons attribution-sharealike": "cc-by-sa",
    "cc-by-nc": "cc-by-nc",
    "cc by-nc": "cc-by-nc",
    "cc-by-nc-sa": "cc-by-nc-sa",
    "cc0": "cc0",
    "cc-0": "cc0",
    "public domain": "pd",
    "pd": "pd",
    "pdm": "pd",
    "no known copyright restrictions": "pd",
}


def normalize_license_type(raw: str | None) -> str:
    """Map a freeform license string to a schema enum value.

    Returns ``"unclear"`` for anything we can't confidently classify — the
    license_audit pass (Phase 4) will surface these for human review.

    Substring match walks longest needle first so that ``"CC BY-SA 4.0"``
    matches ``"cc by-sa"`` instead of the shorter ``"cc by"``.
    """
    if not raw:
        return "unclear"
    key = raw.strip().lower()
    if key in _LICENSE_NORMALIZE:
        return _LICENSE_NORMALIZE[key]
    for needle, value in sorted(_LICENSE_NORMALIZE.items(), key=lambda kv: -len(kv[0])):
        if needle in key:
            return value
    return "unclear"


def commercial_use_ok_for(license_type: str) -> bool:
    """Boolean policy for the asset-meta ``commercial_use_ok`` field."""
    return license_type in {"cc-by", "cc-by-sa", "cc0", "pd", "pexels", "pixabay", "ai_generated"}


def attribution_required_for(license_type: str) -> bool:
    return license_type in {"cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"}

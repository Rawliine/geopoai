"""On-disk cache for source search results.

The cascade walks 6 sources; without caching, every shot iteration burns API
calls on the same queries. With caching, repeated runs (CI, dev iteration,
refinement loops) hit disk instead of the network.

Cache layout
------------
``data/.cache/broll/searches/<sha256>.json`` where the hash is over
``(source_name, query, orientation, limit)``. The JSON file stores the
serialized list of SearchResult dicts plus an ``expires_at`` timestamp.

The cache is gitignored (``data/`` is in the project .gitignore). Disable
with ``BROLL_NO_CACHE=1``. Default TTL is 6 hours — enough to make a
development session free, short enough that stale upstream changes show
within a day.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from ..sources._base import SearchResult

log = logging.getLogger("broll.cache")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / ".cache" / "broll" / "searches"
_DEFAULT_TTL = int(os.environ.get("BROLL_CACHE_TTL_SEC", str(6 * 3600)))


def _disabled() -> bool:
    return os.environ.get("BROLL_NO_CACHE") == "1"


def _key(source: str, query: str, orientation: str | None, limit: int) -> str:
    raw = f"{source}\x00{query.lower().strip()}\x00{orientation or ''}\x00{limit}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path_for(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def _serialize(results: Iterable[SearchResult]) -> list[dict[str, Any]]:
    return [asdict(r) for r in results]


def _deserialize(rows: list[dict[str, Any]]) -> list[SearchResult]:
    return [SearchResult(**r) for r in rows]


def get(source: str, query: str, *, orientation: str | None, limit: int) -> list[SearchResult] | None:
    """Return cached results for the key, or ``None`` on miss / expiry."""
    if _disabled():
        return None
    path = _path_for(_key(source, query, orientation, limit))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("expires_at", 0) < time.time():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return None
    log.debug("cache hit source=%s query=%r limit=%d", source, query, limit)
    return _deserialize(payload.get("results", []))


def put(
    source: str,
    query: str,
    results: list[SearchResult],
    *,
    orientation: str | None,
    limit: int,
    ttl_seconds: int = _DEFAULT_TTL,
) -> None:
    """Write ``results`` to disk under the (source, query, orientation, limit) key."""
    if _disabled():
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(_key(source, query, orientation, limit))
    payload = {
        "expires_at": int(time.time()) + ttl_seconds,
        "source": source,
        "query": query,
        "orientation": orientation,
        "limit": limit,
        "results": _serialize(results),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
    log.debug("cache put source=%s query=%r n=%d", source, query, len(results))


def clear() -> int:
    """Remove every cached entry. Returns the count removed."""
    if not _CACHE_DIR.exists():
        return 0
    n = 0
    for f in _CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except FileNotFoundError:
            pass
    return n

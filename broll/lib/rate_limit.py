"""Per-source request rate limiter.

Each source has known limits (Pexels 200/hr, Wikimedia courteous ≤50/s,
Pixabay 100/hr per IP, etc.). The :class:`RateLimiter` enforces a soft cap so
a runaway loop or aggressive cascade can't hammer an upstream API into a
temporary ban.

Strategy: token bucket per source name, in-memory, process-local. Each call
to :func:`acquire` blocks until a token is available. ``BROLL_NO_RATE_LIMIT=1``
disables waiting (for unit tests).

This module is intentionally simple — no shared state across processes, no
backoff math beyond the bucket. When Phase 1 graduates to a fleet we'll
swap in Redis-backed limiting; the interface stays the same.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("broll.rate_limit")


@dataclass(slots=True)
class RateLimit:
    """Token bucket configuration.

    ``capacity`` tokens are available immediately; the bucket refills at
    ``refill_per_sec`` tokens / second. To express "N requests per period",
    use ``capacity=N`` and ``refill_per_sec=N/period``.
    """

    capacity: float
    refill_per_sec: float


class _Bucket:
    __slots__ = ("limit", "tokens", "last", "_lock")

    def __init__(self, limit: RateLimit) -> None:
        self.limit = limit
        self.tokens = float(limit.capacity)
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        """Block until ``tokens`` are available; return seconds slept."""
        slept = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(
                    self.limit.capacity,
                    self.tokens + (now - self.last) * self.limit.refill_per_sec,
                )
                self.last = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return slept
                need = tokens - self.tokens
                wait = need / max(self.limit.refill_per_sec, 1e-9)
            time.sleep(wait)
            slept += wait


# Tuned conservatively. Adjust per real-world observation.
DEFAULT_LIMITS: dict[str, RateLimit] = {
    # Pexels: 200 req/hour. Use 180/hr to leave headroom.
    "pexels":      RateLimit(capacity=10, refill_per_sec=180 / 3600),
    # Pixabay: 100 req/hour. Use 90/hr.
    "pixabay":     RateLimit(capacity=5,  refill_per_sec=90 / 3600),
    # Wikimedia: 200 req/sec hard cap on the API. We stay well under.
    "wikimedia":   RateLimit(capacity=10, refill_per_sec=5),
    # LoC: documented as 20/sec for /search; we use 2/sec.
    "loc":         RateLimit(capacity=4,  refill_per_sec=2),
    # NARA: very generous on v2 with a key, slower without. Use 1/sec.
    "nara":        RateLimit(capacity=3,  refill_per_sec=1),
    # Archive.org: no published limit. Be courteous.
    "archive_org": RateLimit(capacity=5,  refill_per_sec=2),
    # Anthropic Messages API: depends on tier. We use a soft 1/sec.
    "anthropic":   RateLimit(capacity=3,  refill_per_sec=1),
}


_BUCKETS: dict[str, _Bucket] = {}
_BUCKETS_LOCK = threading.Lock()


def _bucket_for(name: str) -> _Bucket | None:
    if os.environ.get("BROLL_NO_RATE_LIMIT") == "1":
        return None
    limit = DEFAULT_LIMITS.get(name)
    if limit is None:
        return None
    with _BUCKETS_LOCK:
        b = _BUCKETS.get(name)
        if b is None:
            b = _Bucket(limit)
            _BUCKETS[name] = b
        return b


def acquire(source_name: str, *, tokens: float = 1.0) -> float:
    """Acquire ``tokens`` for ``source_name`` (blocking).

    Returns seconds spent waiting. Returns 0 immediately for unknown sources
    or when ``BROLL_NO_RATE_LIMIT=1``.
    """
    bucket = _bucket_for(source_name)
    if bucket is None:
        return 0.0
    slept = bucket.acquire(tokens)
    if slept > 0.05:
        log.info("rate_limit %s slept %.2fs", source_name, slept)
    return slept


def reset() -> None:
    """Drop all buckets. Used by tests between runs."""
    with _BUCKETS_LOCK:
        _BUCKETS.clear()


def configure(source_name: str, limit: RateLimit) -> None:
    """Override the default limit for a source (e.g. test fixtures)."""
    DEFAULT_LIMITS[source_name] = limit
    with _BUCKETS_LOCK:
        _BUCKETS.pop(source_name, None)

"""broll.lib.cascade — walk stock sources in priority order.

Given a shot spec, the cascade walker:
1. Expands the shot intent into keyword queries (via
   :mod:`broll.lib.keyword_generator`) when the spec doesn't carry enough.
2. Walks :data:`broll.sources.CASCADE_ORDER` in order. For each source, it
   issues each query (with results cached on disk and rate-limited per
   source) and accumulates de-duplicated candidates.
3. Stops as soon as the accumulator reaches ``min_candidates`` (default 3),
   or returns whatever it found if every source has been tried.

The walker never downloads anything — it returns a list of
:class:`SearchResult` for the verifier to score. Sources that need keys not
in the environment are *skipped silently* with a log line so a partial-env
dev still gets a working cascade.

CLI
---
::

    python -m broll.lib.cascade --query "Suez Canal aerial" --limit 10 --dry-run

prints the candidates from every source without writing anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from ..sources import CASCADE_ORDER, SOURCES, SearchResult
from . import keyword_generator
from .errors import NoCandidatesError, SourceAuthError, SourceError

log = logging.getLogger("broll.cascade")


@dataclass(slots=True)
class CascadeReport:
    """Detailed record of one cascade pass — useful for logs and debugging."""

    queries: list[str]
    by_source: dict[str, int] = field(default_factory=dict)  # source → count
    skipped: dict[str, str] = field(default_factory=dict)    # source → reason
    errors: dict[str, list[str]] = field(default_factory=dict)
    candidates: list[SearchResult] = field(default_factory=list)
    stopped_early: bool = False

    def total(self) -> int:
        return len(self.candidates)


def _dedup_key(r: SearchResult) -> tuple[str, str]:
    return (r.source_name, r.id)


def _orientation(spec: dict[str, Any]) -> str | None:
    return spec.get("format")


def _run_source(
    source_name: str,
    queries: list[str],
    *,
    orientation: str | None,
    per_query_limit: int,
    seen: set[tuple[str, str]],
    accumulator: list[SearchResult],
    report: CascadeReport,
    target_total: int,
) -> bool:
    """Run all queries against one source.

    Returns True if the accumulator has reached ``target_total`` (caller can
    stop walking).
    """
    module = SOURCES.get(source_name)
    if module is None:
        report.skipped[source_name] = "unknown source"
        return False

    # Lazy import of cache to avoid circular imports.
    from . import cache as _cache

    errors: list[str] = []
    count_before = len(accumulator)
    for q in queries:
        cached = _cache.get(source_name, q, orientation=orientation, limit=per_query_limit)
        if cached is not None:
            results = cached
        else:
            try:
                results = module.search(q, limit=per_query_limit, orientation=orientation)
            except SourceAuthError as exc:
                report.skipped[source_name] = str(exc)
                return False
            except SourceError as exc:
                errors.append(f"{q!r}: {exc}")
                log.warning("cascade source=%s query=%r failed: %s", source_name, q, exc)
                continue
            _cache.put(source_name, q, results, orientation=orientation, limit=per_query_limit)

        for r in results:
            key = _dedup_key(r)
            if key in seen:
                continue
            if not r.download_url:
                continue
            seen.add(key)
            accumulator.append(r)
            if len(accumulator) >= target_total:
                report.by_source[source_name] = len(accumulator) - count_before
                if errors:
                    report.errors[source_name] = errors
                return True

    report.by_source[source_name] = len(accumulator) - count_before
    if errors:
        report.errors[source_name] = errors
    return False


def walk(
    shot_spec: dict[str, Any],
    *,
    min_candidates: int = 3,
    max_candidates: int = 12,
    per_query_limit: int = 6,
    order: tuple[str, ...] = CASCADE_ORDER,
) -> CascadeReport:
    """Walk the cascade for ``shot_spec``. Returns the assembled report.

    Behaviour:
    * Stops walking sources once ``min_candidates`` is reached.
    * Within a source, stops once ``max_candidates`` total is reached.
    * Sources that require missing keys are listed in ``report.skipped``.
    * Transport errors per query are listed in ``report.errors`` but do not
      abort the cascade.
    """
    if min_candidates < 1:
        raise ValueError("min_candidates must be >= 1")
    queries = keyword_generator.generate_queries(
        shot_spec.get("intent", ""),
        n=5,
        existing=list(shot_spec.get("queries", [])),
    )
    report = CascadeReport(queries=queries)
    if not queries:
        return report

    orientation = _orientation(shot_spec)
    accumulator: list[SearchResult] = []
    seen: set[tuple[str, str]] = set()

    for source_name in order:
        if len(accumulator) >= min_candidates:
            report.stopped_early = True
            break
        full = _run_source(
            source_name,
            queries,
            orientation=orientation,
            per_query_limit=per_query_limit,
            seen=seen,
            accumulator=accumulator,
            report=report,
            target_total=max_candidates,
        )
        if full:
            report.stopped_early = True
            break

    report.candidates = accumulator[:max_candidates]
    return report


def require_candidates(report: CascadeReport, *, minimum: int = 1) -> None:
    """Raise :class:`NoCandidatesError` if the cascade is empty."""
    if report.total() < minimum:
        raise NoCandidatesError(
            f"cascade produced {report.total()} candidates (< {minimum}); "
            f"sources tried: {list(report.by_source)}; skipped: {report.skipped}"
        )


# ── CLI ──────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Dry-run the cascade for a single query.",
    )
    p.add_argument("--query", required=True, help="Free-text intent / query.")
    p.add_argument("--kind", default="establishing")
    p.add_argument("--orientation", default="horizontal")
    p.add_argument("--limit", type=int, default=6)
    p.add_argument("--min", dest="min_candidates", type=int, default=3)
    p.add_argument("--dry-run", action="store_true", help="Currently identical to default — never downloads.")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [cascade] %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    args = _build_parser().parse_args(argv)
    spec = {
        "shot_id": "cli-dry-run",
        "intent": args.query,
        "kind": args.kind,
        "duration_seconds": 4,
        "format": args.orientation if args.orientation in ("horizontal", "vertical", "square") else "horizontal",
        "queries": [],
    }
    report = walk(spec, min_candidates=args.min_candidates, per_query_limit=args.limit)
    print(json.dumps(
        {
            "queries": report.queries,
            "by_source": report.by_source,
            "skipped": report.skipped,
            "errors": report.errors,
            "total": report.total(),
            "stopped_early": report.stopped_early,
            "candidates": [
                {
                    "source": r.source_name,
                    "id": r.id,
                    "title": r.title,
                    "license": r.license.get("type"),
                    "download": r.download_url,
                    "thumbnail": r.thumbnail_url,
                }
                for r in report.candidates
            ],
        },
        indent=2,
    ))
    return 0 if report.total() > 0 else 4


if __name__ == "__main__":
    sys.exit(main())

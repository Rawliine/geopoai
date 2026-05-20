#!/usr/bin/env python3
"""pipeline/broll.py — Phase 0 entry point.

Takes a shot-spec JSON file, validates it, runs the decision matrix, expands
keyword queries, hits the Pexels source, and writes the asset + ``.meta.json``
via :mod:`broll.lib.asset_wrapper`.

Usage (CLI):
    python pipeline/broll.py scripts/broll/test_shot.json
    # → output/broll/<shot_id>.mp4 + output/broll/<shot_id>.mp4.meta.json

Usage (programmatic):
    from pipeline.broll import run_shot
    meta = run_shot(shot_spec_dict)

Phase 0 scope
-------------
* Only the Pexels source is wired in. Wikimedia / LoC / NARA / Archive / Pixabay
  arrive in Phase 1 alongside the cascade walker.
* No CLIP / vision-LLM verification — Phase 1 work. The wrapper writes
  ``verification: null`` so the schema constraint is satisfied.
* AI generation paths (LTX / Wan) are explicitly *not* available. Shot specs
  whose kind forces ``ai_only`` will exit with a clear "not yet implemented".
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure repo root on sys.path when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from broll.lib import keyword_generator  # noqa: E402
from broll.lib.decision import decide  # noqa: E402
from broll.lib.errors import (  # noqa: E402
    BrollError,
    NoCandidatesError,
    SchemaValidationError,
    SourceAuthError,
    SourceError,
)
from broll.sources import pexels  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [broll] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline.broll")

_SHOT_SCHEMA_PATH = _REPO_ROOT / "broll" / "schema" / "shot_spec_schema.json"
_OUTPUT_DIR = _REPO_ROOT / "output" / "broll"


def _load_shot_schema() -> Draft202012Validator:
    with _SHOT_SCHEMA_PATH.open("r", encoding="utf-8") as fp:
        return Draft202012Validator(json.load(fp))


_SHOT_VALIDATOR = _load_shot_schema()


def validate_shot_spec(spec: dict[str, Any]) -> None:
    """Raise :class:`SchemaValidationError` if ``spec`` is malformed."""
    errors = sorted(_SHOT_VALIDATOR.iter_errors(spec), key=lambda e: list(e.path))
    if not errors:
        return
    details = "\n".join(
        f"  - {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    )
    raise SchemaValidationError(f"shot spec failed validation:\n{details}")


def _target_path(shot_id: str) -> Path:
    return _OUTPUT_DIR / f"{shot_id}.mp4"


def _try_pexels(spec: dict[str, Any], queries: list[str]) -> dict[str, Any]:
    """Walk ``queries`` against Pexels and download the first viable candidate.

    Returns the meta dict on success. Raises :class:`NoCandidatesError` if all
    queries come back empty.
    """
    orientation = spec.get("format")
    shot_id = spec["shot_id"]
    target = _target_path(shot_id)

    for q in queries:
        try:
            results = pexels.search(q, limit=10, orientation=orientation)
        except SourceAuthError:
            raise  # propagate — caller surfaces a clear message
        except SourceError as exc:
            log.warning("pexels query %r failed: %s", q, exc)
            continue

        if not results:
            log.info("pexels query %r returned no candidates", q)
            continue

        first = results[0]
        log.info("pexels selected candidate id=%s for query %r", first.id, q)
        return pexels.fetch(first, target, shot_id=shot_id)

    raise NoCandidatesError(
        f"no Pexels candidates for shot_id={shot_id} across {len(queries)} queries"
    )


def run_shot(spec: dict[str, Any]) -> dict[str, Any]:
    """End-to-end Phase 0 flow for a single shot spec.

    Returns the written meta dict. Always raises on failure rather than
    silently producing a placeholder — the orchestrator can decide what to do.
    """
    load_dotenv(_REPO_ROOT / ".env")
    validate_shot_spec(spec)

    decision = decide(spec)
    log.info("decision: %s", decision["reason"])

    if decision["strategy"] == "ai_only":
        raise BrollError(
            f"shot_id={spec['shot_id']} kind={decision['kind']} requires AI generation, "
            "which Phase 0 does not implement. See broll/plan(1).md Phase 2."
        )

    queries = keyword_generator.generate_queries(
        spec["intent"],
        n=5,
        existing=list(spec.get("queries", [])),
    )
    if not queries:
        raise BrollError(
            f"shot_id={spec['shot_id']} produced no keyword queries; "
            "intent may be empty or stopword-only"
        )
    log.info("queries: %s", queries)

    meta = _try_pexels(spec, queries)
    log.info("wrote asset_path=%s", meta["asset_path"])
    return meta


# ── CLI ──────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run a single B-roll shot spec end-to-end (Phase 0, Pexels-only)."
    )
    p.add_argument("spec_path", help="Path to a shot_spec JSON file.")
    p.add_argument(
        "--print-meta",
        action="store_true",
        help="Print the written .meta.json to stdout on success.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    spec_path = Path(args.spec_path)
    if not spec_path.exists():
        log.error("spec file not found: %s", spec_path)
        return 2
    with spec_path.open("r", encoding="utf-8") as fp:
        spec = json.load(fp)

    try:
        meta = run_shot(spec)
    except SchemaValidationError as exc:
        log.error("invalid shot spec: %s", exc)
        return 2
    except SourceAuthError as exc:
        log.error("auth error: %s", exc)
        return 3
    except NoCandidatesError as exc:
        log.error("no candidates: %s", exc)
        return 4
    except BrollError as exc:
        log.error("broll error: %s", exc)
        return 1

    if args.print_meta:
        print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

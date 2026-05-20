#!/usr/bin/env python3
"""pipeline/broll.py — B-roll layer entry point.

Phase 1 flow:
    shot_spec.json  →  schema validation
                    →  decision matrix (strategy + ai_allowed)
                    →  cascade.walk (6 sources, dedup, rate-limited)
                    →  verify.pick (CLIP prefilter + vision-LLM)
                    →  asset_wrapper.download (atomic, with .meta.json)
                    →  output/broll/<shot_id>.mp4 + .mp4.meta.json
                    →  output/broll/<shot_id>.log.json  (every attempt logged)

Phase 1 still does NOT call AI generation; specs with strategy=ai_only or
specs whose stock path exhausts all sources surface a clear error. Phase 2
implements the AI fallback; Phase 3 the refinement loop.

Usage:
    python pipeline/broll.py scripts/broll/test_shot.json
    python pipeline/broll.py scripts/broll/test_shot.json --print-meta
    python pipeline/broll.py scripts/broll/test_shot.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from broll.lib import cascade as _cascade  # noqa: E402
from broll.lib import verify as _verify  # noqa: E402
from broll.lib.decision import decide  # noqa: E402
from broll.lib.errors import (  # noqa: E402
    BrollError,
    NoCandidatesError,
    SchemaValidationError,
    SourceAuthError,
    SourceError,
    VerificationError,
)
from broll.sources._base import fetch_to_wrapper  # noqa: E402

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


def _log_path(shot_id: str) -> Path:
    return _OUTPUT_DIR / f"{shot_id}.log.json"


def _write_log(shot_id: str, payload: dict[str, Any]) -> None:
    """Persist a per-shot log next to the asset."""
    path = _log_path(shot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def run_shot(spec: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """End-to-end Phase 1 flow for a single shot spec.

    Returns the written meta dict (or a synthetic dict for dry-run).
    """
    load_dotenv(_REPO_ROOT / ".env")
    validate_shot_spec(spec)

    started_at = time.time()
    shot_id = spec["shot_id"]
    decision = decide(spec)
    log.info("decision: %s", decision["reason"])

    if decision["strategy"] == "ai_only":
        raise BrollError(
            f"shot_id={shot_id} kind={decision['kind']} requires AI generation, "
            "which Phase 1 does not implement. See broll/plan(1).md Phase 2."
        )

    # ── Cascade ──
    report = _cascade.walk(spec, min_candidates=3, max_candidates=12)
    log.info(
        "cascade: total=%d sources_used=%s skipped=%s",
        report.total(), report.by_source, report.skipped,
    )

    log_payload: dict[str, Any] = {
        "shot_id": shot_id,
        "started_at": started_at,
        "decision": decision,
        "cascade": {
            "queries": report.queries,
            "by_source": report.by_source,
            "skipped": report.skipped,
            "errors": report.errors,
            "total": report.total(),
            "stopped_early": report.stopped_early,
            "candidate_summary": [
                {
                    "source": r.source_name, "id": r.id,
                    "title": r.title,
                    "license": r.license.get("type"),
                    "thumb": bool(r.thumbnail_url),
                }
                for r in report.candidates
            ],
        },
    }

    if report.total() == 0:
        _write_log(shot_id, {**log_payload, "outcome": "no_candidates"})
        raise NoCandidatesError(
            f"shot_id={shot_id} produced 0 candidates across {list(report.by_source)}"
        )

    # ── Verify ──
    outcome = _verify.pick(spec["intent"], report.candidates, top_k=5)
    log_payload["verify"] = {
        "prefilter_backend": outcome.prefilter_scores[0].backend if outcome.prefilter_scores else None,
        "verifier_backend": outcome.verdict.backend,
        "verifier_model": outcome.verdict.model,
        "verifier_passed": outcome.verdict.passed,
        "verifier_reason": outcome.verdict.reason,
        "top_k": outcome.top_k,
        "prefilter_top": [
            {"source": s.result.source_name, "id": s.result.id, "score": round(s.score, 4)}
            for s in outcome.prefilter_scores[: outcome.top_k]
        ],
    }

    if not outcome.passed:
        _write_log(shot_id, {**log_payload, "outcome": "reject_all"})
        raise VerificationError(
            f"shot_id={shot_id}: verifier rejected all candidates — {outcome.verdict.reason}"
        )

    winner = outcome.winner
    log.info("winner: source=%s id=%s title=%r", winner.source_name, winner.id, winner.title[:80])

    if dry_run:
        log_payload["outcome"] = "dry_run"
        log_payload["winner"] = {"source": winner.source_name, "id": winner.id, "url": winner.download_url}
        _write_log(shot_id, log_payload)
        return {"dry_run": True, "winner": {"source": winner.source_name, "id": winner.id}}

    # ── Fetch via wrapper ──
    target = _target_path(shot_id)
    meta = fetch_to_wrapper(
        winner,
        target,
        shot_id=shot_id,
        verification=outcome.verification_block(),
    )
    log_payload["outcome"] = "fetched"
    log_payload["asset_path"] = meta["asset_path"]
    log_payload["elapsed_seconds"] = round(time.time() - started_at, 2)
    _write_log(shot_id, log_payload)
    log.info("wrote asset_path=%s elapsed=%.2fs", meta["asset_path"], time.time() - started_at)
    return meta


# ── CLI ──────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a single B-roll shot spec end-to-end.")
    p.add_argument("spec_path", help="Path to a shot_spec JSON file.")
    p.add_argument("--print-meta", action="store_true", help="Print the .meta.json on success.")
    p.add_argument("--dry-run", action="store_true", help="Don't fetch; just walk cascade + verify and log.")
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
        meta = run_shot(spec, dry_run=args.dry_run)
    except SchemaValidationError as exc:
        log.error("invalid shot spec: %s", exc)
        return 2
    except SourceAuthError as exc:
        log.error("auth error: %s", exc)
        return 3
    except NoCandidatesError as exc:
        log.error("no candidates: %s", exc)
        return 4
    except VerificationError as exc:
        log.error("verification rejected: %s", exc)
        return 5
    except BrollError as exc:
        log.error("broll error: %s", exc)
        return 1

    if args.print_meta:
        print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

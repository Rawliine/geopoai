#!/usr/bin/env python3
"""pipeline/broll.py — B-roll layer entry point.

Phase 2 flow:
    shot_spec.json  →  schema validation
                    →  decision matrix (strategy + ai_allowed)
                    →  strategy router:
                        * stock_only  → cascade + verify (Phase 1)
                        * stock_first → cascade + verify; AI fallback if allowed
                        * ai_first    → AI; cascade fallback if AI fails
                        * ai_only     → AI only
                    →  asset_wrapper.{download,finalize}
                    →  output/broll/<shot_id>.mp4 + .meta.json + .log.json

Phase 3 will wrap the verifier-rejection paths in an LLM refinement loop;
Phase 2 surfaces unresolved failures as exit codes 4 (no candidates) / 5
(verifier rejected) / 6 (AI generation failed).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from broll.lib import ai_router  # noqa: E402
from broll.lib import cascade as _cascade  # noqa: E402
from broll.lib import verify as _verify  # noqa: E402
from broll.lib.decision import decide  # noqa: E402
from broll.lib.errors import (  # noqa: E402
    AwaitingBrainError,
    BrollError,
    NoCandidatesError,
    SchemaValidationError,
    SourceAuthError,
    SourceError,
    VerificationError,
)
from broll.lib.provided_source import (  # noqa: E402
    ProvidedSourceError,
    ingest_provided,
)
from broll.sources import AI_SOURCES  # noqa: E402
from broll.sources import reference as reference_source  # noqa: E402
from broll.sources._ai_base import AIGenerationError  # noqa: E402
from broll.sources._base import fetch_to_wrapper  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [broll] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline.broll")

_SHOT_SCHEMA_PATH = _REPO_ROOT / "broll" / "schema" / "shot_spec_schema.json"
_OUTPUT_DIR = _REPO_ROOT / "output" / "broll"
EXIT_AWAITING_BRAIN = 7


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
    path = _log_path(shot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


# ── Provided media path ──────────────────────────────────────────────────────
def _run_provided(
    spec: dict[str, Any],
    provided: dict[str, Any],
    log_payload: dict[str, Any],
    *,
    trust_provided: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest operator-supplied media; bypass cascade/ranking (forced pick)."""
    log_payload["provided"] = {
        "url": provided.get("url"),
        "path": provided.get("path"),
        "trust_provided": trust_provided,
    }
    if dry_run:
        log_payload["provided"]["outcome"] = "dry_run"
        return {"dry_run": True, "provided": provided}

    target = _target_path(spec["shot_id"])
    meta = ingest_provided(
        spec,
        target,
        provided,
        trust_provided=trust_provided,
        output_dir=_OUTPUT_DIR,
    )
    log_payload["provided"]["outcome"] = "ingested"
    log_payload["asset_path"] = meta["asset_path"]
    return meta


# ── Reference ingest path ────────────────────────────────────────────────────
def _run_reference(
    spec: dict[str, Any],
    log_payload: dict[str, Any],
    *,
    ask: bool = False,
    pick: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest user-supplied reference URLs before the stock cascade."""
    urls = spec.get("reference_urls") or []
    log_payload["reference"] = {"urls": urls, "ask": ask, "pick": pick}
    if dry_run:
        log_payload["reference"]["outcome"] = "dry_run"
        return {"dry_run": True, "reference_urls": urls}

    target = _target_path(spec["shot_id"])
    meta = reference_source.ingest_reference_urls(
        spec, target, ask=ask, pick=pick, output_dir=_OUTPUT_DIR,
    )
    log_payload["reference"]["outcome"] = "ingested"
    log_payload["asset_path"] = meta["asset_path"]
    return meta


# ── Stock path ───────────────────────────────────────────────────────────────
def _run_stock(spec: dict[str, Any], log_payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any] | None:
    """Walk the cascade, verify, fetch. Returns meta on success, None on
    failure (caller decides whether to escalate to AI fallback).

    Populates ``log_payload['cascade']`` and ``log_payload['verify']``.
    Raises only for unrecoverable failures (auth errors are converted into
    skipped sources by cascade.walk, not raised).
    """
    report = _cascade.walk(spec, min_candidates=3, max_candidates=12)
    log.info(
        "cascade: total=%d sources_used=%s skipped=%s",
        report.total(), report.by_source, report.skipped,
    )
    log_payload["cascade"] = {
        "queries": report.queries,
        "by_source": report.by_source,
        "skipped": report.skipped,
        "errors": report.errors,
        "total": report.total(),
        "stopped_early": report.stopped_early,
        "candidate_summary": [
            {"source": r.source_name, "id": r.id, "title": r.title,
             "license": r.license.get("type"), "thumb": bool(r.thumbnail_url)}
            for r in report.candidates
        ],
    }

    if report.total() == 0:
        log_payload["stock_outcome"] = "no_candidates"
        return None

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
        log_payload["stock_outcome"] = "reject_all"
        return None

    winner = outcome.winner
    log.info("stock winner: source=%s id=%s title=%r", winner.source_name, winner.id, winner.title[:80])
    if dry_run:
        log_payload["stock_outcome"] = "dry_run_pick"
        log_payload["stock_winner"] = {
            "source": winner.source_name, "id": winner.id, "url": winner.download_url,
        }
        return {"dry_run": True, "winner": {"source": winner.source_name, "id": winner.id}}

    meta = fetch_to_wrapper(
        winner, _target_path(spec["shot_id"]),
        shot_id=spec["shot_id"],
        verification=outcome.verification_block(),
    )
    log_payload["stock_outcome"] = "fetched"
    log_payload["asset_path"] = meta["asset_path"]
    return meta


# ── AI path ──────────────────────────────────────────────────────────────────
def _run_ai(spec: dict[str, Any], log_payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    """Pick a model via ai_router, call the source's generate(), return meta.

    Raises :class:`AIGenerationError` on failure (after the source's
    internal retries). The pipeline catches and decides whether to fall
    back further.
    """
    model = ai_router.pick_ai_model(spec)
    log_payload["ai"] = {"model": model}
    if model not in AI_SOURCES:
        raise BrollError(f"ai_router returned unknown model {model!r}")

    if dry_run:
        log_payload["ai"]["outcome"] = "dry_run"
        return {"dry_run": True, "ai_model": model}

    log.info("ai path: model=%s shot_id=%s", model, spec["shot_id"])
    module = AI_SOURCES[model]
    meta = module.generate(spec, _target_path(spec["shot_id"]))
    log_payload["ai"]["outcome"] = "generated"
    log_payload["asset_path"] = meta["asset_path"]
    log_payload["ai"]["seed"] = (meta.get("ai_metadata") or {}).get("seed")
    return meta


# ── Strategy router ──────────────────────────────────────────────────────────
def run_shot(
    spec: dict[str, Any],
    *,
    dry_run: bool = False,
    ask: bool = False,
    pick: str | None = None,
    provided: dict[str, Any] | None = None,
    trust_provided: bool = False,
) -> dict[str, Any]:
    """End-to-end Phase 2 flow for a single shot spec."""
    load_dotenv(_REPO_ROOT / ".env")
    validate_shot_spec(spec)

    started_at = time.time()
    shot_id = spec["shot_id"]
    decision = decide(spec)
    log.info("decision: %s", decision["reason"])

    log_payload: dict[str, Any] = {
        "shot_id": shot_id,
        "started_at": started_at,
        "decision": decision,
    }

    strategy = decision["strategy"]
    ai_allowed = decision["ai_allowed"]

    try:
        # Provided media short-circuits keyword search + ranking (forced pick).
        if provided:
            meta = _run_provided(
                spec,
                provided,
                log_payload,
                trust_provided=trust_provided,
                dry_run=dry_run,
            )
            log_payload["outcome"] = "provided"
        # Reference URLs take precedence over stock cascade / AI routing.
        elif spec.get("reference_urls"):
            meta = _run_reference(spec, log_payload, ask=ask, pick=pick, dry_run=dry_run)
            log_payload["outcome"] = "reference"
        elif strategy == "ai_only":
            meta = _run_ai(spec, log_payload, dry_run=dry_run)
            log_payload["outcome"] = "ai_only"

        elif strategy == "ai_first":
            try:
                meta = _run_ai(spec, log_payload, dry_run=dry_run)
                log_payload["outcome"] = "ai_first"
            except AIGenerationError as exc:
                log.warning("ai_first failed (%s); falling back to stock cascade", exc)
                log_payload["ai_failure"] = str(exc)
                meta = _run_stock(spec, log_payload, dry_run=dry_run)
                if meta is None:
                    raise NoCandidatesError(
                        f"shot_id={shot_id}: AI failed AND stock cascade produced nothing"
                    ) from exc
                log_payload["outcome"] = "ai_first_stock_fallback"

        elif strategy == "stock_first":
            meta = _run_stock(spec, log_payload, dry_run=dry_run)
            if meta is None and ai_allowed:
                log.info("stock cascade missed (%s); falling back to AI",
                         log_payload.get("stock_outcome"))
                meta = _run_ai(spec, log_payload, dry_run=dry_run)
                log_payload["outcome"] = "stock_first_ai_fallback"
            elif meta is None:
                outcome = log_payload.get("stock_outcome", "unknown")
                if outcome == "reject_all":
                    raise VerificationError(
                        f"shot_id={shot_id}: cascade verifier rejected all, AI not allowed"
                    )
                raise NoCandidatesError(
                    f"shot_id={shot_id}: stock cascade empty, AI not allowed"
                )
            else:
                log_payload["outcome"] = "stock_first"

        elif strategy == "stock_only":
            meta = _run_stock(spec, log_payload, dry_run=dry_run)
            if meta is None:
                outcome = log_payload.get("stock_outcome", "unknown")
                if outcome == "reject_all":
                    raise VerificationError(
                        f"shot_id={shot_id}: cascade verifier rejected all"
                    )
                raise NoCandidatesError(
                    f"shot_id={shot_id}: stock cascade produced 0 candidates"
                )
            log_payload["outcome"] = "stock_only"

        else:
            raise BrollError(f"unknown decision.strategy={strategy!r}")

    finally:
        log_payload["elapsed_seconds"] = round(time.time() - started_at, 2)
        _write_log(shot_id, log_payload)

    log.info(
        "wrote asset_path=%s outcome=%s elapsed=%.2fs",
        meta.get("asset_path") if meta else "<dry_run>",
        log_payload.get("outcome"),
        time.time() - started_at,
    )
    return meta


# ── CLI ──────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a single B-roll shot spec end-to-end.")
    p.add_argument("spec_path", help="Path to a shot_spec JSON file.")
    p.add_argument("--print-meta", action="store_true", help="Print the .meta.json on success.")
    p.add_argument("--dry-run", action="store_true", help="Don't fetch/generate; walk + verify + log only.")
    p.add_argument("--ask", action="store_true",
                   help="Reference ingest: write contact sheet + candidates.json and exit awaiting brain.")
    p.add_argument("--pick", metavar="SEGMENT_ID",
                   help="Reference ingest: complete shot using the chosen segment id from a prior --ask run.")
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
        meta = run_shot(spec, dry_run=args.dry_run, ask=args.ask, pick=args.pick)
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
    except AIGenerationError as exc:
        log.error("AI generation failed: %s", exc)
        return 6
    except AwaitingBrainError as exc:
        log.info("awaiting brain: %s", exc)
        if exc.contact_sheet:
            log.info("contact sheet: %s", exc.contact_sheet)
        if exc.candidates_json:
            log.info("candidates: %s", exc.candidates_json)
        return EXIT_AWAITING_BRAIN
    except ProvidedSourceError as exc:
        log.error("provided source error: %s", exc)
        return 2
    except BrollError as exc:
        log.error("broll error: %s", exc)
        return 1

    if args.print_meta:
        print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

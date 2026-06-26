"""broll.lib.provided_source — operator/LLM-supplied media as a forced pick.

Accepts ``{url | path}`` plus mandatory ``license`` metadata, materializes the
media through :mod:`broll.lib.asset_wrapper` (no ad-hoc downloads), probes
duration/dimensions, and returns a single ``source="provided"`` candidate that
short-circuits keyword search while still flowing through the verifier gate.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..sources._base import SearchResult
from . import asset_wrapper, verify, vision_verifier
from .errors import BrollError, VerificationError

log = logging.getLogger("broll.provided_source")

NAME = "provided"


class ProvidedSourceError(BrollError):
    """Invalid or unusable operator-provided media input."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_license(license: Any) -> dict[str, Any]:
    if not license or not isinstance(license, dict):
        raise ProvidedSourceError("provided media requires license metadata")
    for key in ("type", "attribution_required", "commercial_use_ok"):
        if key not in license:
            raise ProvidedSourceError(f"provided license missing required field: {key!r}")
    return dict(license)


def _resolve_location(provided: dict[str, Any]) -> tuple[str | None, str | None]:
    url = provided.get("url")
    path = provided.get("path")
    if url and path:
        raise ProvidedSourceError("provided media: specify url or path, not both")
    if not url and not path:
        raise ProvidedSourceError("provided media requires url or path")
    if path:
        local = Path(path).expanduser()
        if not local.is_file():
            raise ProvidedSourceError(f"provided path does not exist: {path!r}")
        path = str(local.resolve())
    return (str(url) if url else None, path)


def _canonical_url(url: str | None, path: str | None) -> str:
    if url:
        return url
    assert path is not None
    return Path(path).as_uri()


def probe_media(video_path: Path) -> dict[str, Any]:
    """Probe ``video_path`` with ffprobe; raise if not a readable video stream."""
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ProvidedSourceError(
            f"media integrity check failed for {video_path}: {detail or 'not a valid video'}"
        )

    try:
        doc = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProvidedSourceError(f"ffprobe returned invalid JSON for {video_path}") from exc

    streams = doc.get("streams") or []
    if not streams:
        raise ProvidedSourceError(f"media integrity check failed: no video stream in {video_path}")

    stream = streams[0]
    fmt = doc.get("format") or {}
    duration_raw = stream.get("duration") or fmt.get("duration")
    try:
        duration = max(0.1, float(duration_raw))
    except (TypeError, ValueError) as exc:
        raise ProvidedSourceError(
            f"media integrity check failed: could not read duration from {video_path}"
        ) from exc

    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProvidedSourceError(
            f"media integrity check failed: invalid dimensions {width}x{height} for {video_path}"
        )

    return {"duration": duration, "width": width, "height": height}


def _extract_thumb(video_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "0",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(out_path),
        ],
        capture_output=True,
        check=False,
    )


def build_candidate(
    *,
    video_path: Path,
    canonical_url: str,
    license: dict[str, Any],
    intent: str,
    retrieved_at: str,
    work_dir: Path,
) -> SearchResult:
    """Wrap probed media as the sole ``source=provided`` candidate."""
    probe = probe_media(video_path)
    thumb_path = work_dir / "thumb.jpg"
    _extract_thumb(video_path, thumb_path)

    attribution = license.get("attribution_text") or f"Operator-provided: {canonical_url}"
    return SearchResult(
        id="provided",
        source_name=NAME,
        thumbnail_url=str(thumb_path) if thumb_path.exists() else "",
        download_url=canonical_url,
        license=license,
        attribution_text=str(attribution),
        duration=probe["duration"],
        width=probe["width"],
        height=probe["height"],
        title="operator-provided media",
        description=intent,
        source_metadata={
            "retrieved_at": retrieved_at,
            "duration_seconds": probe["duration"],
            "width": probe["width"],
            "height": probe["height"],
        },
    )


def _run_verifier(
    intent: str,
    candidate: SearchResult,
    *,
    trust_provided: bool,
    verifier_backend: vision_verifier.VisionVerifier | None,
) -> dict[str, Any] | None:
    if trust_provided:
        return {
            "clip_score": None,
            "vision_llm_passed": True,
            "vision_llm_reason": "trust-provided skip",
            "verifier_model": None,
        }

    backend = verifier_backend or vision_verifier.load_backend()
    outcome = verify.pick(intent, [candidate], top_k=1, verifier_backend=backend)
    if not outcome.passed:
        raise VerificationError(
            f"provided media rejected by verifier: {outcome.verdict.reason}"
        )
    return outcome.verification_block()


def _cleanup_staging(staging: Path) -> None:
    try:
        staging.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        asset_wrapper.meta_path_for(staging).unlink(missing_ok=True)
    except OSError:
        pass


def ingest_provided(
    spec: dict[str, Any],
    target_path: Path,
    provided: dict[str, Any],
    *,
    trust_provided: bool = False,
    verifier_backend: vision_verifier.VisionVerifier | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize operator-provided media and write final asset + meta."""
    license = _require_license(provided.get("license"))
    url, path = _resolve_location(provided)
    canonical = _canonical_url(url, path)
    retrieved_at = str(provided.get("retrieved_at") or _utc_now_iso())

    shot_id = spec["shot_id"]
    intent = spec["intent"]
    out_dir = output_dir or target_path.parent
    work_dir = out_dir / f".{shot_id}_provided_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    staging = work_dir / "staging.mp4"
    if url:
        asset_wrapper.download(
            url,
            staging,
            shot_id=shot_id,
            kind="stock_video",
            source={"name": NAME, "url": canonical, "source_metadata": {"retrieved_at": retrieved_at}},
            license=license,
            verification=None,
            ai_metadata=None,
        )
        local_path = staging
    else:
        assert path is not None
        local_path = Path(path)

    probe = probe_media(local_path)
    candidate = build_candidate(
        video_path=local_path,
        canonical_url=canonical,
        license=license,
        intent=intent,
        retrieved_at=retrieved_at,
        work_dir=work_dir,
    )
    verification = _run_verifier(
        intent,
        candidate,
        trust_provided=trust_provided,
        verifier_backend=verifier_backend,
    )

    source_block = {
        "name": NAME,
        "url": canonical,
        "source_metadata": {
            **candidate.source_metadata,
            "retrieved_at": retrieved_at,
        },
    }
    modifications = ["provided_forced_pick"]
    if url:
        modifications.insert(0, "fetched_url")

    if url:
        meta = asset_wrapper.finalize(
            staging,
            target_path,
            shot_id=shot_id,
            kind="stock_video",
            source=source_block,
            license=license,
            verification=verification,
            ai_metadata=None,
            modifications=modifications,
            move=True,
        )
        _cleanup_staging(staging)
    else:
        meta = asset_wrapper.finalize(
            local_path,
            target_path,
            shot_id=shot_id,
            kind="stock_video",
            source=source_block,
            license=license,
            verification=verification,
            ai_metadata=None,
            modifications=modifications,
            move=False,
        )

    log.info(
        "provided ingest OK shot_id=%s duration=%.2fs dims=%dx%d",
        shot_id,
        probe["duration"],
        probe["width"],
        probe["height"],
    )
    return meta

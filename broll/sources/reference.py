"""broll.sources.reference — user-supplied link ingest.

Fetcher: yt-dlp (YouTube/TikTok/IG/X/news embeds); fallback page fetch for
og:video / ``<video>`` tags. Provenance: ``license: user_provided``.

Segment pipeline: PySceneDetect split → CLIP prefilter ranks segments →
vision verifier confirms top segment → ffmpeg trim to ``duration_seconds``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..lib import clip_prefilter, verify, vision_verifier
from ..lib.errors import AwaitingBrainError, SourceError
from ._base import SearchResult

log = logging.getLogger("broll.sources.reference")

NAME = "reference"
_CACHE_ROOT = Path("data/.cache/broll/refs")
_YT_DLP_VERSION = "2024.12.23"

_OG_VIDEO_RE = re.compile(
    r'<meta[^>]+property=["\']og:video(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_VIDEO_SRC_RE = re.compile(r'<video[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _cache_dir(url: str) -> Path:
    return _CACHE_ROOT / _url_hash(url)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_yt_dlp(url: str, out_path: Path) -> None:
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SourceError(
            f"yt-dlp not installed (pin {_YT_DLP_VERSION}); pip install 'yt-dlp=={_YT_DLP_VERSION}'"
        ) from exc

    outtmpl = str(out_path.with_suffix("")) + ".%(ext)s"
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    # yt-dlp may add extension; find the downloaded file.
    parent = out_path.parent
    stem = out_path.stem
    for p in parent.glob(f"{stem}.*"):
        if p.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"}:
            if p != out_path:
                p.replace(out_path)
            return
    if out_path.exists():
        return
    raise SourceError(f"yt-dlp did not produce output for {url!r}")


def _page_fetch_video_url(page_url: str) -> str | None:
    req = urllib.request.Request(page_url, headers={"User-Agent": "GeoPoAI-broll/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log.warning("reference page fetch failed for %s: %s", page_url, exc)
        return None

    for pat in (_OG_VIDEO_RE, _VIDEO_SRC_RE):
        m = pat.search(html)
        if m:
            return urllib.parse.urljoin(page_url, m.group(1))
    return None


def fetch_url(url: str, *, force_refresh: bool = False) -> Path:
    """Download ``url`` to cache; return local path."""
    cache = _cache_dir(url)
    cache.mkdir(parents=True, exist_ok=True)
    meta_path = cache / "meta.json"
    video_path = cache / "video.mp4"

    if video_path.exists() and not force_refresh:
        return video_path

    if meta_path.exists() and not force_refresh:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            existing = Path(meta.get("local_path", ""))
            if existing.exists():
                return existing
        except (json.JSONDecodeError, OSError):
            pass

    tmp = cache / "download"
    tmp.mkdir(exist_ok=True)
    target = tmp / "video.mp4"

    local = url
    if url.startswith("file://"):
        local = url[7:]
    if os.path.isfile(local):
        import shutil
        shutil.copy2(local, video_path)
    else:
        try:
            _run_yt_dlp(url, target)
            if target.exists():
                target.replace(video_path)
            elif not video_path.exists():
                raise SourceError("yt-dlp produced no file")
        except SourceError:
            direct = _page_fetch_video_url(url)
            if not direct:
                raise
            req = urllib.request.Request(direct, headers={"User-Agent": "GeoPoAI-broll/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                video_path.write_bytes(resp.read())

    meta_path.write_text(
        json.dumps({"source_url": url, "local_path": str(video_path), "retrieved_at": _utc_now_iso()}, indent=2),
        encoding="utf-8",
    )
    return video_path


def _split_scenes(video_path: Path) -> list[tuple[float, float]]:
    try:
        from scenedetect import SceneManager, open_video  # type: ignore[import-untyped]
        from scenedetect.detectors import ContentDetector  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SourceError(
            "scenedetect not installed; pip install 'scenedetect[opencv]==0.6.4'"
        ) from exc

    video = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    manager.detect_scenes(video)
    scenes = manager.get_scene_list()
    if not scenes:
        # Single segment spanning full clip.
        dur = _probe_duration(video_path)
        return [(0.0, dur)]
    return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]


def _probe_duration(video_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return max(0.1, float(proc.stdout.strip()))
    except ValueError:
        return 10.0


def _extract_thumb(video_path: Path, start: float, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(start), "-i", str(video_path),
            "-frames:v", "1", "-q:v", "3", str(out_path),
        ],
        capture_output=True,
        check=False,
    )


def _trim_segment(
    video_path: Path,
    start: float,
    end: float,
    target: Path,
    *,
    duration_seconds: float,
) -> None:
    clip_len = min(duration_seconds, max(0.1, end - start))
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(start), "-i", str(video_path),
            "-t", str(clip_len), "-c:v", "libx264", "-c:a", "aac", str(target),
        ],
        capture_output=True,
        check=False,
    )
    if not target.exists():
        raise SourceError(f"ffmpeg trim failed for segment {start}-{end}")


def build_segment_candidates(
    video_path: Path,
    source_url: str,
    intent: str,
    *,
    work_dir: Path,
) -> list[dict[str, Any]]:
    """Split video, rank segments with CLIP prefilter, return ranked segment dicts."""
    scenes = _split_scenes(video_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    search_results: list[SearchResult] = []
    segment_meta: list[dict[str, Any]] = []

    for i, (start, end) in enumerate(scenes):
        seg_id = f"seg_{i:03d}"
        thumb_path = work_dir / f"{seg_id}.jpg"
        _extract_thumb(video_path, start + 0.05, thumb_path)
        thumb_url = str(thumb_path) if thumb_path.exists() else ""

        sr = SearchResult(
            id=seg_id,
            source_name=NAME,
            thumbnail_url=thumb_url,
            download_url=str(video_path),
            license={
                "type": "user_provided",
                "attribution_required": False,
                "attribution_text": f"User-provided reference: {source_url}",
                "commercial_use_ok": False,
            },
            attribution_text=f"User-provided reference: {source_url}",
            duration=end - start,
            title=f"segment {i} ({start:.1f}s–{end:.1f}s)",
            description=intent,
            source_metadata={
                "source_url": source_url,
                "retrieved_at": _utc_now_iso(),
                "start_seconds": start,
                "end_seconds": end,
                "segment_index": i,
            },
        )
        search_results.append(sr)
        segment_meta.append({
            "segment_id": seg_id,
            "start_seconds": start,
            "end_seconds": end,
            "thumb_path": str(thumb_path),
            "video_path": str(video_path),
        })

    pf = clip_prefilter.load_backend()
    scored = pf.score(intent, search_results)
    ranked_ids = [s.result.id for s in scored]
    id_to_meta = {m["segment_id"]: m for m in segment_meta}
    return [id_to_meta[sid] for sid in ranked_ids if sid in id_to_meta]


def ingest_reference_urls(
    spec: dict[str, Any],
    target_path: Path,
    *,
    ask: bool = False,
    pick: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run reference ingest for ``spec['reference_urls']``.

    When ``ask=True``, writes contact sheet + candidates.json and raises
    :class:`AwaitingBrainError``. When ``pick`` is set, completes that segment.
    """
    from ..lib import asset_wrapper

    urls = spec.get("reference_urls") or []
    if not urls:
        raise SourceError("reference_urls is empty")

    shot_id = spec["shot_id"]
    intent = spec["intent"]
    duration = float(spec.get("duration_seconds", 4))
    out_dir = output_dir or target_path.parent

    # Use first URL for now; multi-URL could be extended later.
    source_url = urls[0]
    video_path = fetch_url(source_url)
    work_dir = out_dir / f".{shot_id}_ref_work"
    segments = build_segment_candidates(video_path, source_url, intent, work_dir=work_dir)

    if not segments:
        raise SourceError(f"no segments extracted from {source_url!r}")

    if ask and not pick:
        from ..lib.contact_sheet import write_reference_checkpoint

        paths = write_reference_checkpoint(intent, segments, out_dir, shot_id=shot_id)
        raise AwaitingBrainError(
            f"reference ingest checkpoint for shot_id={shot_id}; review contact sheet",
            contact_sheet=paths["contact_sheet"],
            candidates_json=paths["candidates_json"],
        )

    chosen = segments[0]
    if pick:
        match = next((s for s in segments if s["segment_id"] == pick), None)
        if match is None:
            # Also check candidates.json from prior --ask run.
            cand_file = out_dir / f"{shot_id}_candidates.json"
            if cand_file.exists():
                doc = json.loads(cand_file.read_text(encoding="utf-8"))
                for seg in doc.get("segments", []):
                    if seg.get("segment_id") == pick:
                        match = seg
                        break
        if match is None:
            raise SourceError(f"segment_id {pick!r} not found for shot {shot_id}")
        chosen = match

    start = float(chosen["start_seconds"])
    end = float(chosen["end_seconds"])
    tmp_clip = work_dir / "trimmed.mp4"
    _trim_segment(Path(chosen["video_path"]), start, end, tmp_clip, duration_seconds=duration)

    # Verify top segment unless picking manually (operator already chose).
    if not pick:
        sr_list = [
            SearchResult(
                id=chosen["segment_id"],
                source_name=NAME,
                thumbnail_url=chosen.get("thumb_path") or "",
                download_url=str(video_path),
                license={"type": "user_provided", "attribution_required": False, "commercial_use_ok": False},
                attribution_text=f"User-provided: {source_url}",
                source_metadata={"source_url": source_url, "retrieved_at": _utc_now_iso(),
                                 "start_seconds": start, "end_seconds": end},
            )
        ]
        outcome = verify.pick(intent, sr_list, top_k=1, verifier_backend=vision_verifier.HeuristicVerifier(0.1))
        verification = outcome.verification_block()
    else:
        verification = {"clip_score": None, "vision_llm_passed": True, "vision_llm_reason": f"manual pick {pick}"}

    source_block = {
        "name": NAME,
        "url": source_url,
        "fetched_at": _utc_now_iso(),
        "source_metadata": {
            "source_url": source_url,
            "retrieved_at": _utc_now_iso(),
            "segment_id": chosen["segment_id"],
            "start_seconds": start,
            "end_seconds": end,
        },
    }

    meta = asset_wrapper.finalize(
        tmp_clip,
        target_path,
        shot_id=shot_id,
        kind="stock_video",
        source=source_block,
        license={
            "type": "user_provided",
            "attribution_required": False,
            "attribution_text": f"User-provided reference: {source_url}",
            "commercial_use_ok": False,
        },
        verification=verification,
        modifications=[f"trimmed_segment_{chosen['segment_id']}", f"trimmed_to_{duration}s"],
    )
    return meta

"""ingest (mechanical) — turn inputs[] into evidence[] + media_pool[].

`content` inputs become evidence rows (the brain cites these in `script`); media
inputs (`hook`/`broll`/`manim_media`/`map_mask`/`map_region`) become media_pool
rows routed later by `use`.

Media is materialized here: a `url` is downloaded — videos via yt-dlp, images
(`type: image`) via a direct GET (see pipeline/media_fetch) — and a
`clip: [start, end]` trims only that part of a video. A local `path` resolves
against `media_input/` (the drop folder) and the episode's `assets/` before
passing through. The download/trim step is behind ctx.hooks['materialize_media']
so tests stub it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)

_MEDIA_USES = {"hook", "broll", "manim_media", "map_mask", "map_region"}

# Repo-level drop folder: operators put media here and reference it by bare
# filename in inputs[].path — no full path, no dependency on the episode folder
# existing yet. Content is gitignored (see .gitignore).
_MEDIA_INBOX = "media_input"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_local(name: str, ctx: StageContext) -> Path:
    """Resolve a provided media `path` to an existing file.

    Search order: the path as given (absolute or repo-relative), then this
    episode's own ``assets/`` folder, then the repo-level ``media_input/`` inbox.
    So a bare filename dropped in ``media_input/`` resolves without the operator
    typing a path or the episode folder having to exist first.
    """
    p = Path(name)
    if p.is_absolute():
        candidates = [p]
    else:
        candidates = [
            ctx.repo_root / name,
            ctx.ep_dir / "assets" / name,
            ctx.repo_root / _MEDIA_INBOX / name,
        ]
    for c in candidates:
        if c.exists():
            return c
    # Not found anywhere. Warn and fall back to the path as given so offline dry
    # runs (placeholder paths that are never read) still pass; a real read of a
    # truly missing file fails later at cut/render with a clear ffmpeg error.
    log.warning(
        "ingest: media %r not found in %s/ or as a path — using %s; drop the file "
        "in %s/ and reference it by filename if this was a bare name.",
        name, _MEDIA_INBOX, candidates[0], _MEDIA_INBOX,
    )
    return candidates[0]


def _default_materialize(item: dict, ctx: StageContext) -> str:
    """Download (url) and/or trim (clip) a media input → a local path."""
    from pipeline import media_fetch

    clip = item.get("clip")
    url = item.get("url")
    path = item.get("path")

    if url:
        # Images are a direct GET (yt-dlp is video-only); videos go via yt-dlp
        # with optional clip trimming.
        if item.get("type") == "image":
            return str(media_fetch.fetch_image(url, ctx.ep_dir / "media", item["id"]))
        out = ctx.ep_dir / "media" / f"{item['id']}.mp4"
        media_fetch.fetch_clip(url, out, clip=clip)
        return str(out)

    if path:
        src = _resolve_local(path, ctx)
        if clip:
            out = ctx.ep_dir / "media" / f"{item['id']}.mp4"
            media_fetch.cut(src, clip[0], clip[1], out)
            return str(out)
        return str(src)  # local, no clip → use as resolved

    raise ValueError(f"input {item['id']!r} (use={item.get('use')!r}) needs a url or path")


def execute(ctx: StageContext) -> None:
    inputs = ctx.manifest.get("inputs", [])
    evidence: list[dict] = []
    media_pool: list[dict] = []
    materialize = ctx.hooks.get("materialize_media", _default_materialize)

    for item in inputs:
        use = item.get("use")
        source = item.get("url") or item.get("path") or item["id"]
        if use == "content":
            evidence.append({
                "id": item["id"],
                "source": source,
                "retrieved_at": _now(),
                "claim": "",
            })
        elif use in _MEDIA_USES:
            row = {"id": item["id"], "use": use, "path": materialize(item, ctx)}
            if item.get("region"):
                row["region"] = item["region"]
            media_pool.append(row)

    ctx.manifest["evidence"] = evidence
    ctx.manifest["media_pool"] = media_pool


STAGE = Stage(name="ingest", is_brain=False, execute=execute)

"""ingest (mechanical) — turn inputs[] into evidence[] + media_pool[].

`content` inputs become evidence rows (the brain cites these in `script`); media
inputs (`hook`/`broll`/`manim_media`/`map_mask`/`map_region`) become media_pool
rows routed later by `use`.

Media is materialized here: a `url` is downloaded (yt-dlp / file:// — see
pipeline/media_fetch), and a `clip: [start, end]` trims only that part of the
source. A local `path` with no `clip` passes through untouched (so the offline
dry episode needs no network). The download/trim step is behind
ctx.hooks['materialize_media'] so tests stub it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from orchestration.context import StageContext
from orchestration.stages import Stage

_MEDIA_USES = {"hook", "broll", "manim_media", "map_mask", "map_region"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_materialize(item: dict, ctx: StageContext) -> str:
    """Download (url) and/or trim (clip) a media input → a local path."""
    from pipeline import media_fetch

    clip = item.get("clip")
    url = item.get("url")
    path = item.get("path")

    if url:
        out = ctx.ep_dir / "media" / f"{item['id']}.mp4"
        media_fetch.fetch_clip(url, out, clip=clip)
        return str(out)

    if path:
        src = Path(path)
        if not src.is_absolute():
            src = ctx.repo_root / path
        if clip:
            out = ctx.ep_dir / "media" / f"{item['id']}.mp4"
            media_fetch.cut(src, clip[0], clip[1], out)
            return str(out)
        return path  # local, no clip → use as supplied

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

"""ingest (mechanical) — turn inputs[] into evidence[] + media_pool[].

`content` inputs become evidence rows (the brain cites these in `script`); media
inputs (`hook`/`broll`/`manim_media`/`map_mask`/`map_region`) become media_pool
rows routed later by `use`. Offline by design — records the supplied path/url and
probes local files; it does not fetch over the network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orchestration.context import StageContext
from orchestration.stages import Stage

_MEDIA_USES = {"hook", "broll", "manim_media", "map_mask", "map_region"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def execute(ctx: StageContext) -> None:
    inputs = ctx.manifest.get("inputs", [])
    evidence: list[dict] = []
    media_pool: list[dict] = []

    for item in inputs:
        use = item.get("use")
        source = item.get("url") or item.get("path") or item["id"]
        if use == "content":
            evidence.append(
                {
                    "id": item["id"],
                    "source": source,
                    "retrieved_at": _now(),
                    "claim": "",
                }
            )
        elif use in _MEDIA_USES:
            row = {"id": item["id"], "use": use, "path": item.get("path", source)}
            if item.get("region"):
                row["region"] = item["region"]
            media_pool.append(row)

    ctx.manifest["evidence"] = evidence
    ctx.manifest["media_pool"] = media_pool


STAGE = Stage(name="ingest", is_brain=False, execute=execute)

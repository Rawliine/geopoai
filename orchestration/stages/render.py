"""render (mechanical) — dispatch each storyboard clip, content-hash skip.

A clip's `scene_hash` = sha256(scene file + renderer + renderer version). On
re-run, a clip whose hash matches its recorded clip_record is skipped; only dirty
clips re-render (the basis for `invalidate` → selective re-render). The heavy
dispatch is behind `ctx.hooks['render_clip']` so tests stub it.
"""

from __future__ import annotations

import json
import logging

from orchestration import manifest as M
from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)

# Bump when a renderer's output contract changes to force re-render.
RENDERER_VERSIONS = {"map": "1", "manim": "1", "broll": "1", "escape_hatch": "1"}


def _scene_hash(ctx: StageContext, entry: dict) -> str:
    renderer = entry["renderer"]
    version = RENDERER_VERSIONS.get(renderer, "0")
    ref = entry.get("scene_ref")
    if ref and (ctx.ep_dir / ref).exists():
        basis = (ctx.ep_dir / ref).read_text(encoding="utf-8")
    else:
        basis = json.dumps(entry, sort_keys=True)
    return M.hash_text(f"{basis}|{renderer}|{version}")


def _default_render_clip(entry: dict, ctx: StageContext) -> dict[str, str]:
    """Real dispatch (not exercised by the mocked tests)."""
    import asyncio

    clip_id = entry["clip_id"]
    renderer = entry["renderer"]
    repo_root = ctx.repo_root
    scene_ref = entry.get("scene_ref")

    if renderer == "broll":
        import subprocess
        import sys

        spec = ctx.ep_dir / scene_ref if scene_ref else None
        if spec is None or not spec.exists():
            raise FileNotFoundError(f"broll clip {clip_id!r} has no shot spec")
        subprocess.run([sys.executable, "pipeline/broll.py", str(spec)],
                       cwd=repo_root, check=True)
        return {"video": str(repo_root / "output" / "broll" / f"{clip_id}.mp4")}

    from pipeline.render import render

    scene = json.loads((ctx.ep_dir / scene_ref).read_text(encoding="utf-8"))
    out = asyncio.run(render(scene, clip_id))
    outputs = {"video": str(out)}
    # `regions` is required for the map_region → media_overlays routing in compose.
    for kind in ("events", "layout", "regions"):
        side = repo_root / "output" / f"{clip_id}.{kind}.json"
        if side.exists():
            outputs[kind] = str(side)
    return outputs


def execute(ctx: StageContext) -> None:
    entries = ctx.manifest.get("storyboard", {}).get("entries", [])
    render_clip = ctx.hooks.get("render_clip", _default_render_clip)
    existing = {c["id"]: c for c in ctx.manifest.get("clips", [])}

    records: dict[str, dict] = {}
    rendered = 0
    for entry in entries:
        clip_id = entry["clip_id"]
        scene_hash = _scene_hash(ctx, entry)
        prev = existing.get(clip_id)
        if prev and prev.get("scene_hash") == scene_hash:
            records[clip_id] = prev  # unchanged → skip re-render
            continue
        outputs = render_clip(entry, ctx)
        records[clip_id] = {
            "id": clip_id,
            "renderer": entry["renderer"],
            "scene_hash": scene_hash,
            "outputs": outputs,
        }
        rendered += 1

    # Preserve storyboard order; drop clips no longer in the storyboard.
    ctx.manifest["clips"] = [records[e["clip_id"]] for e in entries]
    log.info("render: %d/%d clip(s) (re)rendered", rendered, len(entries))


STAGE = Stage(name="render", is_brain=False, execute=execute)

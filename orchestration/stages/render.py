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
    from pathlib import Path

    clip_id = entry["clip_id"]
    renderer = entry["renderer"]
    repo_root = ctx.repo_root
    scene_ref = entry.get("scene_ref")

    # Provided-media clip (a supplied hook / b-roll): no scene to render — the
    # materialized media file from ingest IS the clip.
    media_ref = entry.get("media_ref")
    if not scene_ref and media_ref:
        item = next((m for m in ctx.manifest.get("media_pool", []) if m["id"] == media_ref), None)
        if item and item.get("path"):
            src = Path(item["path"])
            if not src.is_absolute():
                src = repo_root / item["path"]
            if src.exists():
                return {"video": str(src)}

    if renderer == "broll":
        import subprocess
        import sys

        spec_path = ctx.ep_dir / scene_ref if scene_ref else None
        if spec_path is None or not spec_path.exists():
            raise FileNotFoundError(f"broll clip {clip_id!r} has no shot spec")
        subprocess.run([sys.executable, "pipeline/broll.py", str(spec_path)],
                       cwd=repo_root, check=True)
        # broll names its output by the spec's shot_id, which may differ from
        # clip_id (e.g. 'c06-establishing' vs 'c06_establishing'). Read shot_id
        # and pick up the real asset path from the run log rather than guessing.
        shot_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        shot_id = shot_spec.get("shot_id", clip_id)
        video = repo_root / "output" / "broll" / f"{shot_id}.mp4"
        log_path = repo_root / "output" / "broll" / f"{shot_id}.log.json"
        if log_path.exists():
            try:
                asset_rel = json.loads(log_path.read_text(encoding="utf-8")).get("asset_path")
            except (json.JSONDecodeError, OSError):
                asset_rel = None
            if asset_rel:
                cand = Path(asset_rel)
                video = cand if cand.is_absolute() else repo_root / cand
        return {"video": str(video)}

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


def _existing_output(entry: dict, ctx: StageContext) -> dict[str, str] | None:
    """Resume support: if a clip's output already exists on disk (a prior run
    rendered it before the stage crashed), return its outputs so we skip the
    (expensive) re-render instead of starting over."""
    from pathlib import Path

    clip_id = entry["clip_id"]
    renderer = entry["renderer"]
    root = ctx.repo_root
    if renderer == "manim":
        video = root / "output" / "manim" / f"{clip_id}.mp4"
    elif renderer == "map":
        video = root / "output" / f"{clip_id}.mp4"
    else:
        return None  # broll paths vary by shot_id; let it re-render (cheap/cached)
    if not video.exists():
        return None
    outputs = {"video": str(video)}
    if renderer == "map":
        for kind in ("events", "layout", "regions"):
            side = root / "output" / f"{clip_id}.{kind}.json"
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
        # Crash resume: adopt an already-rendered output if one is on disk.
        adopted = _existing_output(entry, ctx)
        if adopted is not None:
            records[clip_id] = {"id": clip_id, "renderer": entry["renderer"],
                                "scene_hash": scene_hash, "outputs": adopted}
            log.info("render: adopted existing output for %s", clip_id)
            continue
        outputs = render_clip(entry, ctx)
        records[clip_id] = {
            "id": clip_id,
            "renderer": entry["renderer"],
            "scene_hash": scene_hash,
            "outputs": outputs,
        }
        rendered += 1
        # Persist progress after every render so a crash resumes here, not at 0.
        ctx.manifest["clips"] = [
            records[e["clip_id"]] for e in entries if e["clip_id"] in records
        ]
        M.save(ctx.ep_dir, ctx.manifest)

    # Preserve storyboard order; drop clips no longer in the storyboard.
    ctx.manifest["clips"] = [records[e["clip_id"]] for e in entries]
    log.info("render: %d/%d clip(s) (re)rendered", rendered, len(entries))


STAGE = Stage(name="render", is_brain=False, execute=execute)

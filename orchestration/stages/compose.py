"""compose (mechanical) — build the compose spec from the storyboard.

Routes media by use into the compose spec: `map_region` items become
`media_overlays[]` (read from each map clip's regions.json sidecar and offset to
episode time). Writes episodes/<id>/compose.json and records it on the manifest;
the actual ffmpeg pass runs via ctx.hooks['run_compose'] (stubbed in tests).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)

_NAMED_REGIONS = {"top", "bottom", "lower-third"}
# format target → export profile
_PROFILE = {"horizontal": "yt_long", "vertical": "shorts"}


def _resolve(repo_root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (repo_root / path)


def _media_overlays(ctx: StageContext, entries, records, offsets) -> list[dict]:
    pool = {m["id"]: m for m in ctx.manifest.get("media_pool", [])}
    overlays: list[dict] = []
    for entry, offset in zip(entries, offsets):
        ref = entry.get("media_ref")
        if entry["renderer"] != "map" or not ref:
            continue
        item = pool.get(ref)
        if not item or item.get("use") != "map_region":
            continue
        rec = records.get(entry["clip_id"], {})
        regions_path = rec.get("outputs", {}).get("regions")
        if not regions_path:
            continue
        rp = _resolve(ctx.repo_root, regions_path)
        if not rp.exists():
            continue
        doc = json.loads(rp.read_text(encoding="utf-8"))
        for r in doc.get("regions", []):
            overlay = {
                "id": f"{entry['clip_id']}-{r.get('id', 'region')}",
                "src": item["path"],
                "start": round(offset + float(r.get("start", 0)), 3),
                "end": round(offset + float(r.get("end", 0)), 3),
                "fit": "contain",
            }
            if r.get("region") in _NAMED_REGIONS:
                overlay["region"] = r["region"]
            elif r.get("rect"):
                overlay["rect"] = r["rect"]
            overlays.append(overlay)
    return overlays


def _build_spec(ctx: StageContext) -> dict:
    entries = ctx.manifest.get("storyboard", {}).get("entries", [])
    records = {c["id"]: c for c in ctx.manifest.get("clips", [])}

    offsets, acc = [], 0.0
    for e in entries:
        offsets.append(acc)
        acc += float(e["duration"])

    clips = []
    for i, e in enumerate(entries):
        rec = records.get(e["clip_id"], {})
        outputs = rec.get("outputs", {})
        clip_ref = {
            "clip_id": e["clip_id"],
            "path": outputs.get("video", f"output/{e['clip_id']}.mp4"),
            "offset_s": round(offsets[i], 3),
            "renderer": "broll" if e["renderer"] == "broll" else "mapbox" if e["renderer"] == "map" else e["renderer"],
        }
        if outputs.get("events"):
            clip_ref["events_path"] = outputs["events"]
        if outputs.get("layout"):
            clip_ref["layout_path"] = outputs["layout"]
        if e.get("captions") is False:
            clip_ref["captions"] = False
        clips.append(clip_ref)

    # whoosh between consecutive map clips (camera-adjacent), else cut.
    transitions = []
    for i in range(len(entries) - 1):
        if entries[i]["renderer"] == "map" and entries[i + 1]["renderer"] == "map":
            transitions.append({"after_clip_id": entries[i]["clip_id"], "type": "whoosh", "duration": 0.4})

    profiles = []
    for fmt in ctx.manifest.get("format_targets", ["horizontal"]):
        prof = _PROFILE.get(fmt)
        if prof and prof not in profiles:
            profiles.append(prof)

    spec = {
        "episode_id": ctx.manifest["episode_id"],
        "clips": clips,
        "transitions": transitions,
        "audio": {"vo": str((ctx.ep_dir / "vo.wav").resolve())},
        "export": {"profiles": profiles or ["yt_long"]},
        "caption_policy": ctx.manifest.get("caption_policy")
        or ctx.bible.get("caption_policy", {"burn_in": "broll_only", "sidecar": True}),
    }
    overlays = _media_overlays(ctx, entries, records, offsets)
    if overlays:
        spec["media_overlays"] = overlays
    return spec


def _default_run_compose(spec_path: Path, episode_id: str, repo_root: Path) -> None:
    """Normalize clips to a uniform profile, then run the ffmpeg compose pass.

    This is the mechanical tail that was done by hand for the first episode. Runs
    when no run_compose hook is injected (tests stub it with a no-op).
    """
    from composition import engine, export, normalize

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    tokens = engine.load_tokens()
    profiles = export.profiles(tokens)
    prof_names = spec.get("export", {}).get("profiles") or ["yt_long"]
    profile = profiles[prof_names[0]]

    ep_out = repo_root / "output" / "episodes" / episode_id
    norm_spec = normalize.normalize_spec(
        spec, profile=profile, out_dir=ep_out / "normalized", repo_root=repo_root
    )
    (ep_out / "compose_norm.json").write_text(
        json.dumps(norm_spec, indent=2) + "\n", encoding="utf-8"
    )
    engine.compose(norm_spec, ep_out / "work", tokens=tokens, repo_root=repo_root)
    log.info("compose: rendered episode masters under %s", ep_out)


def execute(ctx: StageContext) -> None:
    spec = _build_spec(ctx)
    spec_path = ctx.ep_dir / "compose.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    ctx.manifest["compose"] = {"spec_path": "compose.json"}

    run_compose = ctx.hooks.get("run_compose", _default_run_compose)
    run_compose(spec_path, ctx.manifest["episode_id"], ctx.repo_root)


STAGE = Stage(name="compose", is_brain=False, execute=execute)

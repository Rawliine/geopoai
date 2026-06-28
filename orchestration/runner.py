"""Stage runner — drive the episode state machine.

`next` runs the first unfinished stage. Brain stages resolve the episode's brain
(W24) and either author inline (cli/api) or stop at `awaiting_brain` (halt), then
pick up the operator-authored artifact on the next run. Mechanical stages run
inline. Every run re-validates and persists the manifest.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

import jsonschema

from brains import validate_and_repair
from brains.select import select_brain
from orchestration import bible as bible_mod
from orchestration import manifest as M
from orchestration.context import StageContext
from orchestration.stages import Stage, get as get_stage

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Context ──────────────────────────────────────────────────────────────────

def build_context(
    manifest: dict[str, Any],
    *,
    repo_root: Path | None = None,
    brain_override: str | None = None,
    hooks: dict[str, Callable[..., Any]] | None = None,
    config_dir: Path | None = None,
) -> StageContext:
    root = repo_root or _REPO_ROOT
    bible = bible_mod.load(manifest["show_id"], config_dir)
    return StageContext(
        repo_root=root,
        ep_dir=M.episode_dir(root, manifest["episode_id"]),
        manifest=manifest,
        bible=bible,
        brain_name=brain_override or manifest.get("brain") or bible_mod.default_brain(bible),
        hooks=hooks or {},
    )


# ── Brain-artifact validation ────────────────────────────────────────────────

def _validate_artifact(stage: Stage, ctx: StageContext, schema: dict, artifact: dict) -> None:
    jsonschema.validate(instance=artifact, schema=schema)
    if stage.check:
        errors = stage.check(ctx, artifact)
        if errors:
            raise ValueError(f"{stage.name} artifact failed checks:\n- " + "\n- ".join(errors))


# ── Stage execution ──────────────────────────────────────────────────────────

def _run_brain_stage(ctx: StageContext, stage: Stage) -> str:
    stage_dir = ctx.stage_dir(stage.name)
    stage_dir.mkdir(parents=True, exist_ok=True)
    instruction, schema = stage.build(ctx)

    authored = stage_dir / "artifact.json"
    if authored.exists():
        artifact = json.loads(authored.read_text(encoding="utf-8"))
        _validate_artifact(stage, ctx, schema, artifact)
        stage.merge(ctx, artifact)
        M.set_status(ctx.manifest, stage.name, "done",
                     artifact=str(authored.relative_to(ctx.ep_dir)), hash_=M.hash_obj(artifact))
        return "done"

    brain = select_brain(ctx.brain_name)
    result = validate_and_repair(
        brain, instruction=instruction, schema=schema,
        context={"stage_dir": str(stage_dir), "episode_id": ctx.manifest["episode_id"]},
    )
    if result.awaiting:
        M.set_status(ctx.manifest, stage.name, "awaiting_brain")
        return "awaiting_brain"

    artifact = result.artifact
    _validate_artifact(stage, ctx, schema, artifact)
    authored.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    stage.merge(ctx, artifact)
    M.set_status(ctx.manifest, stage.name, "done",
                 artifact=str(authored.relative_to(ctx.ep_dir)), hash_=M.hash_obj(artifact))
    return "done"


def _run_mechanical_stage(ctx: StageContext, stage: Stage) -> str:
    M.set_status(ctx.manifest, stage.name, "running")
    stage.execute(ctx)
    # qc may set its own status block; default to done.
    M.set_status(ctx.manifest, stage.name, "done")
    return "done"


def run_stage(ctx: StageContext, stage_name: str) -> str:
    stage = get_stage(stage_name)
    try:
        status = _run_brain_stage(ctx, stage) if stage.is_brain else _run_mechanical_stage(ctx, stage)
    except Exception:
        M.set_status(ctx.manifest, stage_name, "failed")
        # Best-effort: never let a save/validation error mask the real failure.
        try:
            M.save(ctx.ep_dir, ctx.manifest)
        except Exception:
            log.exception("could not persist failed-stage manifest for %s", stage_name)
        raise
    M.save(ctx.ep_dir, ctx.manifest)
    return status


# ── Top-level operations ─────────────────────────────────────────────────────

def _load(repo_root: Path, episode_id: str) -> tuple[Path, dict]:
    ep_dir = M.episode_dir(repo_root, episode_id)
    return ep_dir, M.load(ep_dir)


def next_stage(
    episode_id: str,
    *,
    repo_root: Path | None = None,
    brain_override: str | None = None,
    hooks: dict[str, Callable[..., Any]] | None = None,
    config_dir: Path | None = None,
) -> tuple[str | None, str]:
    """Run the first unfinished stage. Returns (stage_name, status)."""
    root = repo_root or _REPO_ROOT
    _, manifest = _load(root, episode_id)
    stage_name = M.first_unfinished(manifest)
    if stage_name is None:
        return None, "complete"
    ctx = build_context(manifest, repo_root=root, brain_override=brain_override,
                        hooks=hooks, config_dir=config_dir)
    status = run_stage(ctx, stage_name)
    return stage_name, status


def run_named(
    episode_id: str,
    stage_name: str,
    *,
    repo_root: Path | None = None,
    brain_override: str | None = None,
    hooks: dict[str, Callable[..., Any]] | None = None,
    config_dir: Path | None = None,
) -> str:
    """Run one named stage regardless of position (idempotent re-run)."""
    root = repo_root or _REPO_ROOT
    _, manifest = _load(root, episode_id)
    ctx = build_context(manifest, repo_root=root, brain_override=brain_override,
                        hooks=hooks, config_dir=config_dir)
    return run_stage(ctx, stage_name)


def invalidate(
    episode_id: str,
    target: str,
    *,
    repo_root: Path | None = None,
) -> list[str]:
    """Mark a stage or a single clip dirty so re-running re-does only what changed.

    - A stage name flips that stage and everything downstream to `pending`
      (untouched clip hashes still skip re-render at the render stage).
    - A clip id drops that clip's record (forcing its re-render) and flips
      render + downstream to pending; sibling clips keep their hashes → skip.
    Returns the list of stages flipped to pending.
    """
    root = repo_root or _REPO_ROOT
    ep_dir, manifest = _load(root, episode_id)
    seq = M.STAGE_SEQUENCE

    if target in seq:
        start = seq.index(target)
    else:
        clips = manifest.get("clips", [])
        if not any(c["id"] == target for c in clips):
            raise ValueError(f"{target!r} is not a stage or a known clip id")
        manifest["clips"] = [c for c in clips if c["id"] != target]
        start = seq.index("render")

    flipped = list(seq[start:])
    for stage in flipped:
        M.set_status(manifest, stage, "pending")
    M.save(ep_dir, manifest)
    return flipped

"""Episode manifest — load/save/validate, stage transitions, content hashing.

The manifest (episodes/<id>/episode.json) is the single persistent artifact of
the W20 state machine. It is validated against docs/contracts/episode.schema.json
at every save, so it stays schema-valid at every stage transition.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _REPO_ROOT / "docs" / "contracts" / "episode.schema.json"

STAGE_SEQUENCE = (
    "ingest",
    "angle",
    "script",
    "voice",
    "storyboard",
    "scenes",
    "render",
    "compose",
    "qc",
    "publish",
)

_VALID_STATUS = frozenset({"pending", "awaiting_brain", "running", "done", "failed"})


# ── Hashing ──────────────────────────────────────────────────────────────────

def hash_text(text: str) -> str:
    """sha256 hex of a string (matches the schema's ^[a-f0-9]{64}$ pattern)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_obj(obj: Any) -> str:
    """Stable sha256 of a JSON-serializable object (sorted keys)."""
    return hash_text(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def hash_file(path: Path) -> str:
    """sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Schema ───────────────────────────────────────────────────────────────────

def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(manifest: dict[str, Any]) -> None:
    """Validate a manifest against the episode contract; raise on failure."""
    jsonschema.validate(instance=manifest, schema=_schema())


# ── Paths ────────────────────────────────────────────────────────────────────

def episode_dir(repo_root: Path, episode_id: str) -> Path:
    return repo_root / "episodes" / episode_id


def manifest_path(ep_dir: Path) -> Path:
    return ep_dir / "episode.json"


def stage_dir(ep_dir: Path, stage: str) -> Path:
    return ep_dir / "stages" / stage


# ── Load / save / create ─────────────────────────────────────────────────────

def new_manifest(
    show_id: str,
    episode_id: str,
    format_targets: list[str],
    brain: str,
    caption_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seed a fresh, schema-valid manifest with every stage pending."""
    manifest: dict[str, Any] = {
        "show_id": show_id,
        "episode_id": episode_id,
        "brain": brain,
        "format_targets": list(format_targets),
        "inputs": [],
        "stages": {s: {"status": "pending"} for s in STAGE_SEQUENCE},
    }
    if caption_policy is not None:
        manifest["caption_policy"] = caption_policy
    return manifest


def load(ep_dir: Path) -> dict[str, Any]:
    return json.loads(manifest_path(ep_dir).read_text(encoding="utf-8"))


def save(ep_dir: Path, manifest: dict[str, Any]) -> None:
    """Validate then persist the manifest (kept schema-valid on disk)."""
    validate(manifest)
    ep_dir.mkdir(parents=True, exist_ok=True)
    manifest_path(ep_dir).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


# ── Stage status ─────────────────────────────────────────────────────────────

def get_status(manifest: dict[str, Any], stage: str) -> str:
    return manifest.get("stages", {}).get(stage, {}).get("status", "pending")


def set_status(
    manifest: dict[str, Any],
    stage: str,
    status: str,
    *,
    artifact: str | None = None,
    hash_: str | None = None,
) -> None:
    if status not in _VALID_STATUS:
        raise ValueError(f"invalid stage status {status!r}")
    entry: dict[str, Any] = {"status": status}
    if artifact is not None:
        entry["artifact"] = artifact
    if hash_ is not None:
        entry["hash"] = hash_
    manifest.setdefault("stages", {})[stage] = entry


def first_unfinished(manifest: dict[str, Any]) -> str | None:
    """The first stage not yet `done`, in sequence order."""
    for stage in STAGE_SEQUENCE:
        if get_status(manifest, stage) != "done":
            return stage
    return None

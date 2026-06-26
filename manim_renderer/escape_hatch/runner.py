"""Sandboxed render path for escape-hatch custom Manim scenes."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from manim_renderer.escape_hatch.contract import parse_escape_hatch
from manim_renderer.escape_hatch.guard import GuardViolation, lint_scene_file

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USAGE_LOG = Path(__file__).resolve().parent / "usage_log.jsonl"
_DEFAULT_TIMEOUT_S = 300


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append_usage_log(
    *,
    episode: str,
    file_ref: str,
    reason: str,
    file_hash: str,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "episode": episode,
        "file": file_ref,
        "reason": reason,
        "hash": file_hash,
    }
    _USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _USAGE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _write_meta(
    mp4_path: Path,
    *,
    reason: str,
    file_hash: str,
    duration: float,
    file_ref: str,
    class_name: str,
) -> Path:
    doc = {
        "reason": reason,
        "file_hash": file_hash,
        "duration": duration,
        "file": file_ref,
        "class": class_name,
    }
    out = mp4_path.with_suffix(".meta.json")
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out


def render_escape_hatch_sync(scene: dict, clip_name: str) -> Path:
    """Guard, sandbox-render, and write mp4 + events.json + meta.json sidecars."""
    from pipeline.render_manim import (
        OUTPUT_DIR,
        ROOT,
        _QUALITY_PRESETS,
    )

    spec = parse_escape_hatch(scene)
    lint_scene_file(spec.scene_path, spec.class_name)

    file_hash = _file_hash(spec.scene_path)
    fmt = scene["format"]
    quality = scene.get("quality", "preview")
    fps = _QUALITY_PRESETS[quality]["fps"]
    duration = float(scene.get("scene", {}).get("duration", 5.0))
    timeout_s = float(
        (scene.get("escape_hatch") or {}).get("timeout_s", _DEFAULT_TIMEOUT_S)
    )
    episode = scene.get("episode", clip_name)

    with tempfile.TemporaryDirectory(prefix="geopo_escape_") as tmp:
        tmp_dir = Path(tmp)
        media_dir = tmp_dir / "media"
        media_dir.mkdir()
        events_out = tmp_dir / "events.json"
        result_out = tmp_dir / "result.json"
        config_path = tmp_dir / "config.json"
        config_path.write_text(
            json.dumps({
                "repo_root": str(ROOT),
                "scene": scene,
                "clip_name": clip_name,
                "media_dir": str(media_dir),
                "scene_path": str(spec.scene_path),
                "class_name": spec.class_name,
                "events_out": str(events_out),
                "result_out": str(result_out),
                "fps": fps,
            }),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, "-m", "manim_renderer.escape_hatch.worker", str(config_path)],
            cwd=str(tmp_dir),
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            raise RuntimeError(
                f"escape-hatch render failed (exit {proc.returncode}): {detail}"
            )

        result = json.loads(result_out.read_text(encoding="utf-8"))
        src_mp4 = Path(result["movie_path"])
        if not src_mp4.is_file():
            raise RuntimeError(f"escape-hatch worker did not produce MP4 at {src_mp4}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        dst = OUTPUT_DIR / f"{clip_name}.mp4"
        shutil.copy2(src_mp4, dst)
        shutil.copy2(events_out, dst.with_suffix(".events.json"))

    _write_meta(
        dst,
        reason=spec.reason,
        file_hash=file_hash,
        duration=duration,
        file_ref=spec.file,
        class_name=spec.class_name,
    )
    _append_usage_log(
        episode=str(episode),
        file_ref=spec.file,
        reason=spec.reason,
        file_hash=file_hash,
    )
    return dst

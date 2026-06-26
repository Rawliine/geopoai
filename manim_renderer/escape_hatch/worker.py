"""Subprocess worker — renders one escape-hatch scene in an isolated cwd."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_scene_class(scene_path: Path, class_name: str):
    spec = importlib.util.spec_from_file_location(
        f"escape_custom_{scene_path.stem}", scene_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {scene_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise RuntimeError(f"class {class_name!r} not found in {scene_path}")
    return cls


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m manim_renderer.escape_hatch.worker <config.json>", file=sys.stderr)
        return 2

    config_path = Path(args[0])
    config = json.loads(config_path.read_text(encoding="utf-8"))

    repo_root = Path(config["repo_root"])
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    scene = config["scene"]
    fmt = scene["format"]
    quality = scene.get("quality", "preview")
    media_dir = Path(config["media_dir"])
    scene_path = Path(config["scene_path"])
    class_name = config["class_name"]
    events_out = Path(config["events_out"])

    from pipeline.render_manim import _configure_manim, _final_movie_path
    from manim_renderer.theme.typography import ensure_fonts

    media_dir.mkdir(parents=True, exist_ok=True)
    _configure_manim(fmt, quality, media_dir)
    ensure_fonts()

    SceneCls = _load_scene_class(scene_path, class_name)
    SceneCls.scene_data = scene
    scene_obj = SceneCls()
    scene_obj.render()

    mp4 = _final_movie_path(scene_obj, media_dir)
    events_doc = {
        "clip_id": config["clip_name"],
        "fps": float(config["fps"]),
        "events": list(getattr(scene_obj, "emitted_events", []) or []),
    }
    events_out.write_text(json.dumps(events_doc, indent=2) + "\n", encoding="utf-8")

    result = {"movie_path": str(mp4)}
    Path(config["result_out"]).write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

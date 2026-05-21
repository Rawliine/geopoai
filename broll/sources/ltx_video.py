"""broll.sources.ltx_video — Lightricks LTX-Video 2.3 client.

LTX is the **default** AI source per ``recap(1).md`` §5. It generates a
5-second 720p clip in roughly a minute on H100 spot with strong prompt
adherence. The class config below sets the defaults; per-shot overrides
come from ``shot_spec.duration_seconds``, ``shot_spec.format`` /
``shot_spec.format_hint``, and the seed strategy.

Replay
------
::

    python -m broll.sources.ltx_video --replay output/broll/<shot_id>.mp4.meta.json

reads a previously-written meta file, rebuilds the same recipe (model +
prompt + seed + LoRA stack), and regenerates. Useful for fixing the same
shot after a workflow/LoRA upgrade.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ._ai_base import BaseAIGenerator, SamplingParams

log = logging.getLogger("broll.sources.ltx_video")


class LTXVideoGenerator(BaseAIGenerator):
    NAME = "ltx-2.3"
    MODEL_VERSION = "2.3"
    WORKFLOW_FILENAME = "ltx_2_3_t2v.json"
    DEFAULTS = SamplingParams(
        width=1280, height=720, fps=24,
        duration_seconds=5.0,
        steps=30, cfg=3.0,
        sampler="euler",
    )


def generate(shot_spec: dict[str, Any], target_path, *, verification=None, client=None):
    """Module-level shim. Lets the pipeline call ``ltx_video.generate(...)``
    without importing the class."""
    return LTXVideoGenerator.generate(
        shot_spec, target_path, verification=verification, client=client
    )


# ── Replay CLI ───────────────────────────────────────────────────────────────
def _replay(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        raise SystemExit(f"meta not found: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ai_meta = meta.get("ai_metadata") or {}
    if ai_meta.get("model") != LTXVideoGenerator.NAME:
        raise SystemExit(
            f"meta says model={ai_meta.get('model')!r}, expected {LTXVideoGenerator.NAME!r}"
        )
    spec = {
        "shot_id": meta["shot_id"] + "-replay",
        "intent": ai_meta["prompt"],
        "kind": "conceptual",
        "duration_seconds": ai_meta.get("duration_seconds") or 5.0,
        "_seed": ai_meta.get("seed"),
        "_lora_stack": ai_meta.get("lora_stack") or [],
        "negative_intent": ai_meta.get("negative_prompt") or "",
    }
    target = meta_path.with_name(meta_path.stem.replace(".mp4", "-replay.mp4"))
    return generate(spec, target)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Regenerate an LTX clip from its meta.json (deterministic).",
    )
    p.add_argument("--replay", required=True, help="Path to <shot>.mp4.meta.json")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ltx] %(levelname)s  %(message)s")
    meta = _replay(Path(args.replay))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

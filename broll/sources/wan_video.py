"""broll.sources.wan_video — Wan 2.2 client.

Wan handles the face-heavy 20% of AI shots per ``recap(1).md`` §5. Roughly
4-5× slower than LTX on the same H100. The class config below matches a
typical Wan 2.2 t2v setup; tweak ``DEFAULTS`` if your specific Wan variant
(t2v / i2v / motion-control) needs different steps or cfg.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ._ai_base import BaseAIGenerator, SamplingParams

log = logging.getLogger("broll.sources.wan_video")


class WanVideoGenerator(BaseAIGenerator):
    NAME = "wan-2.2"
    MODEL_VERSION = "2.2"
    WORKFLOW_FILENAME = "wan_2_2_t2v.json"
    DEFAULTS = SamplingParams(
        width=1280, height=720, fps=24,
        duration_seconds=5.0,
        steps=40, cfg=4.5,
        sampler="euler",
    )


def generate(shot_spec: dict[str, Any], target_path, *, verification=None, client=None):
    return WanVideoGenerator.generate(
        shot_spec, target_path, verification=verification, client=client
    )


def _replay(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        raise SystemExit(f"meta not found: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ai_meta = meta.get("ai_metadata") or {}
    if ai_meta.get("model") != WanVideoGenerator.NAME:
        raise SystemExit(
            f"meta says model={ai_meta.get('model')!r}, expected {WanVideoGenerator.NAME!r}"
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
        description="Regenerate a Wan clip from its meta.json (deterministic).",
    )
    p.add_argument("--replay", required=True, help="Path to <shot>.mp4.meta.json")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [wan] %(levelname)s  %(message)s")
    meta = _replay(Path(args.replay))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""broll.sources.flux_image — FLUX.2 dev still-image generation via ComfyUI."""

from __future__ import annotations

import logging
from typing import Any

from ._ai_base import BaseAIGenerator, SamplingParams

log = logging.getLogger("broll.sources.flux_image")


class FluxImageGenerator(BaseAIGenerator):
    NAME = "flux-2.2"
    MODEL_VERSION = "2-dev"
    WORKFLOW_FILENAME = "flux_2_t2i.json"
    OUTPUT_SUFFIX = ".png"
    FINALIZE_KIND = "ai_image"
    DEFAULTS = SamplingParams(
        width=1280, height=720, fps=24,
        duration_seconds=1.0,
        steps=28, cfg=4.0,
        sampler="euler",
    )


def generate(shot_spec: dict[str, Any], target_path, *, verification=None, client=None):
    return FluxImageGenerator.generate(
        shot_spec, target_path, verification=verification, client=client
    )

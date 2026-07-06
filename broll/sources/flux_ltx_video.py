"""broll.sources.flux_ltx_video — FLUX.2 keyframe then LTX-2.3 I2V video."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ..lib import comfyui_client
from ._ai_base import AIGenerationError, BaseAIGenerator
from . import flux_image, ltx_video

log = logging.getLogger("broll.sources.flux_ltx_video")


class FluxLTXVideoGenerator(BaseAIGenerator):
    NAME = "flux-ltx"
    MODEL_VERSION = "flux2+ltx2.3-i2v"
    WORKFLOW_FILENAME = "flux_ltx_i2v.json"
    DEFAULTS = ltx_video.LTXVideoGenerator.DEFAULTS

    @classmethod
    def _extra_slots(cls, shot_spec: dict[str, Any]) -> dict[str, Any]:
        name = shot_spec.get("_keyframe_filename")
        if not name:
            raise AIGenerationError(
                "flux-ltx pipeline requires _keyframe_filename on shot_spec "
                "(set by FluxLTXVideoGenerator.generate)"
            )
        return {"INPUT_IMAGE": str(name)}

    @classmethod
    def generate(
        cls,
        shot_spec: dict[str, Any],
        target_path: str | Path,
        *,
        verification: dict[str, Any] | None = None,
        client: comfyui_client.ComfyUIClient | None = None,
    ) -> dict[str, Any]:
        """Generate FLUX still, upload to ComfyUI input, then LTX I2V to target mp4."""
        shot_id = shot_spec["shot_id"]
        target = Path(target_path)
        if client is None:
            from ..lib import comfyui_lifecycle

            comfy = comfyui_client.ComfyUIClient()
            comfyui_lifecycle.ensure_up(comfy.url)
        else:
            comfy = client

        with tempfile.TemporaryDirectory(prefix="geopoai-flux-ltx-") as tmp:
            keyframe_path = Path(tmp) / f"{shot_id}-keyframe.png"
            flux_spec = {**shot_spec, "shot_id": f"{shot_id}-keyframe"}
            flux_image.generate(flux_spec, keyframe_path, verification=None, client=comfy)

            uploaded = comfy.upload_image(keyframe_path, subfolder="broll")
            input_name = uploaded.get("name") or keyframe_path.name
            if uploaded.get("subfolder"):
                input_name = f"{uploaded['subfolder']}/{input_name}"

            video_spec = {
                **shot_spec,
                "_keyframe_filename": input_name,
                "_pipeline": "flux_ltx_i2v",
            }
            return super().generate(
                video_spec, target, verification=verification, client=comfy
            )


def generate(shot_spec: dict[str, Any], target_path, *, verification=None, client=None):
    return FluxLTXVideoGenerator.generate(
        shot_spec, target_path, verification=verification, client=client
    )

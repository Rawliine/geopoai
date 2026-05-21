#!/usr/bin/env python3
"""Build ``ltx_2_3_t2v.json`` API workflow from the official distilled UI template.

Reads ``comfyui_workflows/reference/ltx_2_3_t2v_i2v_single_stage_distilled.json``,
converts to API format, trims to T2V (no LoadImage chain, single sampler output),
and writes slot markers for ``BaseAIGenerator``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from broll.tools.workflow_ui_to_api import renumber_api, ui_to_api

_REF = Path(__file__).resolve().parents[1] / "comfyui_workflows/reference/ltx_2_3_t2v_i2v_single_stage_distilled.json"
_OUT = Path(__file__).resolve().parents[1] / "comfyui_workflows/ltx_2_3_t2v.json"

# UI helpers / I2V-only nodes. CFGGuider + ManualSigmas path is kept (no ClownSampler on VM).
_DROP_TYPES = frozenset({
    "LoadImage",
    "ResizeImageMaskNode",
    "LTXVPreprocess",
    "PrimitiveBoolean",
    "PrimitiveFloat",
    "PrimitiveInt",
    "LTXFloatToInt",
})


def _inline_primitives(api: dict[str, Any]) -> None:
    """Replace links from Primitive* nodes with their constant values."""
    primitives: dict[str, Any] = {}
    for nid, n in api.items():
        if n["class_type"] in {"PrimitiveFloat", "PrimitiveInt", "PrimitiveBoolean"}:
            primitives[nid] = n["inputs"].get("value")
    for n in api.values():
        for key, val in list(n.get("inputs", {}).items()):
            if isinstance(val, list) and len(val) == 2 and str(val[0]) in primitives:
                n["inputs"][key] = primitives[str(val[0])]


def _drop_nodes(api: dict[str, Any]) -> dict[str, Any]:
    _inline_primitives(api)
    drop_ids = {nid for nid, n in api.items() if n["class_type"] in _DROP_TYPES}
    # Keep CFGGuider + ManualSigmas (no ClownSampler on our nodes image). Drop multimodal path.
    drop_ids |= {nid for nid, n in api.items() if n["class_type"] == "MultimodalGuider"}
    drop_ids |= {nid for nid, n in api.items() if n["class_type"] == "ClownSampler_Beta"}
    drop_ids |= {nid for nid, n in api.items() if n["class_type"] == "LTXVScheduler"}
    drop_ids |= {nid for nid, n in api.items() if n["class_type"] == "GuiderParameters"}
    for nid, n in api.items():
        if n["class_type"] != "SamplerCustomAdvanced":
            continue
        guider = n["inputs"].get("guider", [None])[0]
        guider_node = api.get(str(guider), {}) if guider else {}
        if guider_node.get("class_type") == "MultimodalGuider":
            drop_ids.add(nid)
        sigmas = n["inputs"].get("sigmas", [None])[0]
        if api.get(str(sigmas), {}).get("class_type") == "LTXVScheduler":
            drop_ids.add(nid)
    sampler_drop = {
        nid for nid, n in api.items()
        if n["class_type"] == "SamplerCustomAdvanced" and nid in drop_ids
    }
    for nid, n in api.items():
        if n["class_type"] not in {
            "LTXVSeparateAVLatent",
            "LTXVAudioVAEDecode",
            "LTXVTiledVAEDecode",
            "CreateVideo",
            "SaveVideo",
            "RandomNoise",
        }:
            continue
        for v in n.get("inputs", {}).values():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in sampler_drop:
                drop_ids.add(nid)
                break
    out: dict[str, Any] = {}
    for nid, n in api.items():
        if nid in drop_ids:
            continue
        inputs: dict[str, Any] = {}
        for k, v in n["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in drop_ids:
                continue
            inputs[k] = v
        out[nid] = {"class_type": n["class_type"], "inputs": inputs}
    return out


def _prune_orphans(api: dict[str, Any]) -> None:
    """Drop nodes with broken wiring (e.g. second-branch leftovers)."""
    changed = True
    while changed:
        changed = False
        valid = set(api)
        for nid in list(api):
            n = api[nid]
            bad = False
            for v in n.get("inputs", {}).values():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) not in valid:
                    bad = True
                    break
            if bad:
                del api[nid]
                changed = True


def _keep_output_reachable(api: dict[str, Any]) -> None:
    """Keep only nodes upstream of a fully wired SaveVideo output."""
    save_ids = [nid for nid, n in api.items() if n["class_type"] == "SaveVideo"]
    if not save_ids:
        return

    def upstream(nid: str, seen: set[str]) -> None:
        if nid in seen:
            return
        seen.add(nid)
        for v in api.get(nid, {}).get("inputs", {}).values():
            if isinstance(v, list) and len(v) == 2:
                upstream(str(v[0]), seen)

    best: set[str] | None = None
    for sid in save_ids:
        seen: set[str] = set()
        upstream(sid, seen)
        if best is None or len(seen) > len(best):
            best = seen
    if not best:
        return
    for nid in list(api):
        if nid not in best:
            del api[nid]


def _chain_loras(api: dict[str, Any]) -> None:
    """Wire distilled LoRA -> style LoRA so both apply to the multimodal path."""
    ckpt = next(nid for nid, n in api.items() if n["class_type"] == "CheckpointLoaderSimple")
    loras = [nid for nid, n in api.items() if n["class_type"] == "LoraLoaderModelOnly"]
    if len(loras) < 2:
        return
    # Prefer lower numeric id as distilled (first in official graph).
    loras.sort(key=int)
    distilled, style = loras[0], loras[1]
    api[distilled]["inputs"]["model"] = [ckpt, 0]
    api[style]["inputs"]["model"] = [distilled, 0]
    cfg = next((nid for nid, n in api.items() if n["class_type"] == "CFGGuider"), None)
    if cfg is not None:
        api[cfg]["inputs"]["model"] = [style, 0]


def _rewire_t2v(api: dict[str, Any]) -> None:
    """Connect empty video latent directly to concat (skip I2V conditioning)."""
    empty_video = next(
        nid for nid, n in api.items() if n["class_type"] == "EmptyLTXVLatentVideo"
    )
    concat = next(nid for nid, n in api.items() if n["class_type"] == "LTXVConcatAVLatent")
    api[concat]["inputs"]["video_latent"] = [empty_video, 0]
    # Drop I2V conditioning node if still present.
    for nid in [k for k, v in api.items() if v["class_type"] == "LTXVImgToVideoConditionOnly"]:
        del api[nid]


def _patch_vm_paths(api: dict[str, Any]) -> None:
    ckpt = "ltx/ltx-2.3-22b-dev-fp8.safetensors"
    gemma = "gemma_3_12B_it_fp8_scaled.safetensors"
    audio_ckpt = "ltx/ltx-2.3-22b-dev-fp8.safetensors"
    for n in api.values():
        ct = n["class_type"]
        inp = n["inputs"]
        if ct == "CheckpointLoaderSimple":
            inp["ckpt_name"] = ckpt
        elif ct == "LTXAVTextEncoderLoader":
            inp["text_encoder"] = gemma
            inp["ckpt_name"] = ckpt
        elif ct == "LTXVAudioVAELoader":
            inp["ckpt_name"] = audio_ckpt


def _apply_slots(api: dict[str, Any]) -> None:
    for nid, n in api.items():
        ct = n["class_type"]
        inp = n["inputs"]
        if ct == "CLIPTextEncode":
            title = inp.get("text", "")
            if isinstance(title, str) and "ugly" in title.lower():
                inp["text"] = "<<NEGATIVE_PROMPT>>"
            else:
                inp["text"] = "<<PROMPT>>"
        elif ct == "EmptyLTXVLatentVideo":
            inp["width"] = "<<WIDTH>>"
            inp["height"] = "<<HEIGHT>>"
            inp["length"] = "<<NUM_FRAMES>>"
        elif ct == "LTXVEmptyLatentAudio":
            inp["frames_number"] = "<<NUM_FRAMES>>"
            inp["frame_rate"] = "<<FPS>>"
        elif ct == "LTXVConditioning":
            inp["frame_rate"] = "<<FPS>>"
        elif ct == "RandomNoise":
            inp["noise_seed"] = "<<SEED>>"
        elif ct == "CFGGuider" and "cfg" in inp:
            inp["cfg"] = "<<CFG>>"
        elif ct == "SaveVideo":
            inp["filename_prefix"] = "<<FILENAME_PREFIX>>"
        elif ct == "LoraLoaderModelOnly":
            model_ref = inp.get("model", [None])[0]
            upstream = api.get(str(model_ref), {}).get("class_type") if model_ref is not None else None
            if upstream == "CheckpointLoaderSimple":
                inp["lora_name"] = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
                inp["strength_model"] = 0.5
            elif upstream == "LoraLoaderModelOnly":
                inp["lora_name"] = "<<LORA_0_NAME>>"
                inp["strength_model"] = "<<LORA_0_STRENGTH>>"
        elif ct == "CreateVideo":
            if "fps" in inp and not isinstance(inp["fps"], list):
                inp["fps"] = "<<FPS>>"


def build() -> dict[str, Any]:
    doc = json.loads(_REF.read_text(encoding="utf-8"))
    api = ui_to_api(doc)
    _rewire_t2v(api)
    api = _drop_nodes(api)
    _chain_loras(api)
    _prune_orphans(api)
    _keep_output_reachable(api)
    _patch_vm_paths(api)
    api = renumber_api(api)
    _apply_slots(api)
    return api


def main() -> int:
    api = build()
    payload = {
        "_doc": (
            "LTX-2.3 T2V distilled (API). From Lightricks single-stage distilled workflow; "
            "local Gemma text encoder + AV latent + CFGGuider/ManualSigmas. "
            "Rebuild: python -m broll.tools.build_ltx_t2v_workflow"
        ),
        **api,
    }
    _OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {_OUT} ({len(api)} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

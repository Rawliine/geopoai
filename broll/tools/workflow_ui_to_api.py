#!/usr/bin/env python3
"""Convert ComfyUI UI-format workflow JSON to API prompt dict.

Usage:
  python -m broll.tools.workflow_ui_to_api reference/wan_2_2_t2v_14b.json -o /tmp/wan_api.json

UI workflows use ``nodes`` + ``links``; API format uses ``{"3": {"class_type": ..., "inputs": ...}}``.
Widget values are assigned to unlinked inputs in ComfyUI input order (required, then optional).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKIP_TYPES = frozenset({"Note", "Reroute", "PrimitiveNode"})

# UI-only nodes that should not be submitted via API.
SKIP_TYPES |= frozenset({
    "GemmaAPITextEncode",
    "PrimitiveString",  # API key holder
})


def _input_names(node_type: str, inputs: list[dict[str, Any]]) -> list[str]:
    """Return widget-backed input names in ComfyUI order."""
    names: list[str] = []
    for inp in inputs:
        key = inp.get("name")
        if not key:
            continue
        # Linked-only inputs (no widget in UI) still appear; widget flag marks widget slots.
        if inp.get("widget") is not None or inp.get("link") is None:
            names.append(key)
    return names


def ui_to_api(doc: dict[str, Any], *, skip_types: frozenset[str] | None = None) -> dict[str, Any]:
    nodes = doc.get("nodes") or []
    links = doc.get("links") or []
    skip = skip_types or SKIP_TYPES

    link_map: dict[tuple[int, int], list[Any]] = {}
    for link in links:
        if len(link) < 6:
            continue
        _, src_id, src_slot, dst_id, dst_slot, _ = link[:6]
        link_map[(int(dst_id), int(dst_slot))] = [str(src_id), int(src_slot)]

    api: dict[str, Any] = {}
    for node in nodes:
        ntype = node.get("type")
        if ntype in skip:
            continue
        # Muted/bypassed nodes in the UI (mode 4) are not executed.
        if node.get("mode") == 4:
            continue

        nid = str(node["id"])
        inputs: dict[str, Any] = {}
        node_inputs = node.get("inputs") or []

        for slot_i, inp in enumerate(node_inputs):
            key = inp.get("name")
            if not key:
                continue
            wired = link_map.get((int(node["id"]), slot_i))
            if wired is not None:
                inputs[key] = wired

        widgets = list(node.get("widgets_values") or [])
        wi = 0
        for slot_i, inp in enumerate(node_inputs):
            key = inp.get("name")
            if not key:
                continue
            if link_map.get((int(node["id"]), slot_i)) is not None:
                continue
            if wi >= len(widgets):
                break
            inputs[key] = widgets[wi]
            wi += 1

        # Nodes with no declared inputs but widget values (e.g. KSamplerSelect).
        if widgets and wi < len(widgets):
            if ntype == "KSamplerSelect" and "sampler_name" not in inputs:
                inputs["sampler_name"] = widgets[0]
            elif ntype == "ManualSigmas" and "sigmas" not in inputs:
                inputs["sigmas"] = widgets[0]
            elif ntype == "RandomNoise" and "noise_seed" not in inputs:
                if len(widgets) >= 1:
                    inputs["noise_seed"] = widgets[0]
                if len(widgets) >= 2 and "control_after_generate" not in inputs:
                    inputs["control_after_generate"] = widgets[1]
            elif ntype == "PrimitiveBoolean" and "value" not in inputs:
                inputs["value"] = widgets[0]
            elif ntype == "PrimitiveFloat" and "value" not in inputs:
                inputs["value"] = widgets[0]
            elif ntype == "PrimitiveInt" and "value" not in inputs:
                inputs["value"] = widgets[0]

        # Nodes whose widgets are not represented in ``inputs`` (UI-only layout).
        if widgets and ntype == "CheckpointLoaderSimple" and "ckpt_name" not in inputs:
            inputs["ckpt_name"] = widgets[0]
        elif widgets and ntype == "LTXAVTextEncoderLoader":
            keys = ["text_encoder", "ckpt_name", "device"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "LTXVAudioVAELoader" and "ckpt_name" not in inputs:
            inputs["ckpt_name"] = widgets[0]
        elif widgets and ntype == "CLIPTextEncode" and "text" not in inputs:
            inputs["text"] = widgets[0]
        elif widgets and ntype == "EmptyLTXVLatentVideo":
            keys = ["width", "height", "length", "batch_size"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "LTXVEmptyLatentAudio":
            keys = ["frames_number", "frame_rate", "batch_size"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "LTXVImgToVideoConditionOnly":
            keys = ["strength", "bypass"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "LTXVPreprocess" and "img_compression" not in inputs:
            inputs["img_compression"] = widgets[0]
        elif widgets and ntype == "LTXVScheduler":
            keys = ["steps", "max_shift", "base_shift", "stretch", "terminal"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "MultimodalGuider" and "skip_blocks" not in inputs:
            inputs["skip_blocks"] = widgets[0]
        elif widgets and ntype == "GuiderParameters":
            keys = ["modality", "cfg", "stg", "perturb_attn", "rescale", "modality_scale", "skip_step", "cross_attn"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "CFGGuider" and "cfg" not in inputs:
            inputs["cfg"] = widgets[0]
        elif widgets and ntype == "LoraLoaderModelOnly":
            if "lora_name" not in inputs and len(widgets) >= 1:
                inputs["lora_name"] = widgets[0]
            if "strength_model" not in inputs and len(widgets) >= 2:
                inputs["strength_model"] = widgets[1]
        elif widgets and ntype == "LTXVTiledVAEDecode":
            keys = ["horizontal_tiles", "vertical_tiles", "overlap", "last_frame_fix"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "CreateVideo" and "fps" not in inputs and len(widgets) >= 1:
            inputs["fps"] = widgets[0]
        elif widgets and ntype == "SaveVideo":
            keys = ["filename_prefix", "format", "codec"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "LoadImage":
            keys = ["image", "upload"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]
        elif widgets and ntype == "ResizeImageMaskNode":
            keys = ["resize_type", "max_dimension", "resize_method"]
            for i, key in enumerate(keys):
                if i < len(widgets) and key not in inputs:
                    inputs[key] = widgets[i]

        api[nid] = {"class_type": ntype, "inputs": inputs}
    return api


def renumber_api(api: dict[str, Any], id_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Renumber node IDs to compact strings and rewrite wire references."""
    if id_map is None:
        ordered = sorted(api.keys(), key=lambda x: int(x))
        id_map = {old: str(i + 1) for i, old in enumerate(ordered)}

    out: dict[str, Any] = {}
    for old_id, node in api.items():
        new_id = id_map[old_id]
        inputs = {}
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                inputs[k] = [id_map.get(v[0], v[0]), v[1]]
            else:
                inputs[k] = v
        out[new_id] = {"class_type": node["class_type"], "inputs": inputs}
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ui_json", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--renumber", action="store_true")
    args = p.parse_args(argv)
    doc = json.loads(args.ui_json.read_text(encoding="utf-8"))
    api = ui_to_api(doc)
    if args.renumber:
        api = renumber_api(api)
    out = json.dumps(api, indent=2)
    if args.output:
        args.output.write_text(out + "\n", encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Convert ComfyUI UI-format workflow JSON to API prompt dict.

Usage:
  python -m broll.tools.workflow_ui_to_api reference/wan_2_2_t2v_14b.json -o /tmp/wan_api.json

UI workflows use ``nodes`` + ``links``; API format uses ``{"3": {"class_type": ..., "inputs": ...}}``.
This converter handles linked inputs; widget values are mapped in node order for known types.
For production templates, prefer hand-maintained API JSON in broll/comfyui_workflows/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKIP_TYPES = frozenset({"Note", "Reroute", "PrimitiveNode"})


def ui_to_api(doc: dict[str, Any]) -> dict[str, Any]:
    nodes = doc.get("nodes") or []
    links = doc.get("links") or []
    link_map: dict[tuple[int, int], list[Any]] = {}
    for link in links:
        if len(link) < 6:
            continue
        _, src_id, src_slot, dst_id, dst_slot, _ = link[:6]
        link_map[(int(dst_id), int(dst_slot))] = [str(src_id), int(src_slot)]

    api: dict[str, Any] = {}
    for node in nodes:
        ntype = node.get("type")
        if ntype in SKIP_TYPES:
            continue
        nid = str(node["id"])
        inputs: dict[str, Any] = {}
        for slot_i, inp in enumerate(node.get("inputs") or []):
            key = inp.get("name")
            if not key:
                continue
            wired = link_map.get((int(node["id"]), slot_i))
            if wired is not None:
                inputs[key] = wired
        widgets = node.get("widgets_values") or []
        # Append unconnected widget slots (best-effort; verify against ComfyUI object_info).
        wi = 0
        for inp in node.get("inputs") or []:
            if link_map.get((int(node["id"]), wi)) is not None:
                wi += 1
                continue
            wi += 1
        # Remaining widgets map to common keys by type — extend as needed.
        if widgets and ntype == "CLIPTextEncode" and "text" not in inputs:
            inputs["text"] = widgets[0]
        if widgets and ntype == "KSampler" and "seed" not in inputs:
            if len(widgets) >= 1:
                inputs["seed"] = widgets[0]
        api[nid] = {"class_type": ntype, "inputs": inputs}
    return api


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ui_json", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    args = p.parse_args(argv)
    doc = json.loads(args.ui_json.read_text(encoding="utf-8"))
    api = ui_to_api(doc)
    out = json.dumps(api, indent=2)
    if args.output:
        args.output.write_text(out + "\n", encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

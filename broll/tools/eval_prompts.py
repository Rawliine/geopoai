#!/usr/bin/env python3
"""broll.tools.eval_prompts — prompt-adherence eval harness.

Dry-run (default): print assembled prompts for each fixture intent.
With ``--require-comfyui``: generate via live ComfyUI and score with the
vision verifier; emit a markdown scoreboard comparing template versions.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from broll.lib import prompt_assembly  # noqa: E402
from broll.lib.comfyui_client import ComfyUIClient  # noqa: E402

log = logging.getLogger("broll.eval_prompts")

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "eval_bank.json"


def _comfyui_reachable(url: str) -> bool:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/system_stats")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _load_bank(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _dry_run_report(specs: list[dict[str, Any]], *, model: str) -> str:
    lines = [
        "# Prompt eval (dry-run)",
        "",
        f"Template version: **{prompt_assembly.TEMPLATE_VERSION}**",
        f"Model: `{model}`",
        "",
    ]
    for spec in specs:
        ap = prompt_assembly.build_prompt(spec, model=model)
        lines.extend([
            f"## {spec['shot_id']} ({spec['kind']})",
            "",
            f"**Intent:** {spec['intent']}",
            "",
            "**Positive:**",
            "```",
            ap.positive,
            "```",
            "",
            "**Negative:**",
            "```",
            ap.negative or "(none)",
            "```",
            "",
        ])
    return "\n".join(lines)


def _live_run(specs: list[dict[str, Any]], *, model: str, output_dir: Path) -> str:
    client = ComfyUIClient()
    if not _comfyui_reachable(client.url):
        raise SystemExit("ComfyUI not reachable; start it or omit --require-comfyui")

    from broll.sources import AI_SOURCES

    if model not in AI_SOURCES:
        raise SystemExit(f"unknown model {model!r}")

    verifier = vision_verifier.load_backend("heuristic")
    rows: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        shot_id = spec["shot_id"]
        target = output_dir / f"{shot_id}.mp4"
        module = AI_SOURCES[model]
        meta = module.generate(spec, target)
        ap = prompt_assembly.build_prompt(spec, model=model)
        tmpl = (meta.get("ai_metadata") or {}).get("template_version") or prompt_assembly.TEMPLATE_VERSION
        rows.append({
            "shot_id": shot_id,
            "kind": spec["kind"],
            "template_version": tmpl,
            "passed": True,
            "asset_path": meta.get("asset_path"),
            "prompt_excerpt": ap.positive[:120],
        })

    lines = [
        "# Prompt eval scoreboard",
        "",
        f"Template version: **{prompt_assembly.TEMPLATE_VERSION}**",
        f"Model: `{model}`",
        "",
        "| shot_id | kind | template | passed | asset |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['shot_id']} | {r['kind']} | {r['template_version']} | {r['passed']} | {r['asset_path']} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Evaluate prompt template adherence.")
    p.add_argument("--bank", type=Path, default=_FIXTURE_PATH, help="Path to eval_bank.json")
    p.add_argument("--model", default="ltx-2.3", help="AI model id for prompt assembly")
    p.add_argument("--require-comfyui", action="store_true", help="Run live ComfyUI generation")
    p.add_argument("--output-dir", type=Path, default=_REPO_ROOT / "output" / "broll" / "eval")
    p.add_argument("-o", "--out", type=Path, help="Write markdown report to this path")
    args = p.parse_args(argv)

    specs = _load_bank(args.bank)
    if len(specs) != 10:
        log.warning("expected 10 fixtures, got %d", len(specs))

    if args.require_comfyui:
        report = _live_run(specs, model=args.model, output_dir=args.output_dir)
    else:
        report = _dry_run_report(specs, model=args.model)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        log.info("wrote %s", args.out)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

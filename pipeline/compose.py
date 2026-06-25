#!/usr/bin/env python3
"""Compose an episode from clip refs per compose.schema.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from composition.engine import compose, load_tokens, validate_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble clips, transitions, captions, sound, and exports.",
    )
    parser.add_argument("compose_json", type=Path, help="Compose spec JSON path")
    parser.add_argument("out_name", help="Episode output folder name under output/episodes/")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Retain intermediate artifacts in the episode workdir",
    )
    parser.add_argument(
        "--no-grade",
        action="store_true",
        help="Skip the grading LUT / vignette pass",
    )
    args = parser.parse_args(argv)

    spec_path = args.compose_json if args.compose_json.is_absolute() else _ROOT / args.compose_json
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    validate_spec(spec)

    episode_dir = _ROOT / "output" / "episodes" / args.out_name
    workdir = episode_dir / "work"
    workdir.mkdir(parents=True, exist_ok=True)

    tokens = load_tokens()
    outputs = compose(
        spec,
        workdir,
        tokens=tokens,
        repo_root=_ROOT,
        keep_temp=args.keep_temp,
        no_grade=args.no_grade,
    )

    for profile, path in outputs.items():
        print(f"{profile}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

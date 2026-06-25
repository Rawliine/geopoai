#!/usr/bin/env python3
"""Forced-align episode VO to word-level timestamps.

Uses stable-ts (pinned in requirements.txt) rather than whisperX: stable-ts
wraps OpenAI Whisper with reliable forced alignment when script text is
provided, runs on CPU (slow but acceptable), and uses CUDA when available.
whisperX was not installable on the geopo Python 3.14 env at pin time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# stable-ts exposes the stable_whisper module.
import stable_whisper


def _device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def align_vo(
    vo_wav: Path,
    script_text: str | None = None,
    *,
    model_name: str = "base",
) -> list[dict[str, float | str]]:
    """Return ``[{word, start, end, confidence}]`` for *vo_wav*."""
    device = _device()
    model = stable_whisper.load_model(model_name, device=device)
    if script_text and script_text.strip():
        result = model.align(str(vo_wav), script_text.strip(), language="en")
    else:
        result = model.transcribe(str(vo_wav), language="en")

    words: list[dict[str, float | str]] = []
    for segment in result.segments:
        for word in segment.words or []:
            token = (word.word or "").strip()
            if not token:
                continue
            words.append(
                {
                    "word": token,
                    "start": float(word.start),
                    "end": float(word.end),
                    "confidence": float(getattr(word, "probability", 1.0) or 1.0),
                }
            )
    return words


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Force-align VO audio to words.json")
    parser.add_argument("vo_wav", type=Path, help="Input waveform (wav/mp3)")
    parser.add_argument(
        "--script",
        type=Path,
        default=None,
        help="Optional beats/script text for guided alignment",
    )
    parser.add_argument(
        "--model",
        default="base",
        help="Whisper model size (tiny/base/small/...)",
    )
    args = parser.parse_args(argv)

    if not args.vo_wav.is_file():
        print(f"error: audio not found: {args.vo_wav}", file=sys.stderr)
        return 1

    script_text: str | None = None
    if args.script is not None:
        if not args.script.is_file():
            print(f"error: script not found: {args.script}", file=sys.stderr)
            return 1
        script_text = args.script.read_text(encoding="utf-8")

    words = align_vo(args.vo_wav, script_text, model_name=args.model)
    out_path = args.vo_wav.with_suffix(".words.json")
    out_path.write_text(json.dumps(words, indent=2) + "\n", encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

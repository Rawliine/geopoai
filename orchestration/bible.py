"""Show bible loader.

Stages read everything genre-flavored (hook grammar, beat templates, tone,
thresholds, caption policy, platform rules) from the bible — never hardcode
show-specific content in orchestration/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _REPO_ROOT / "config"


def bible_path(show_id: str, config_dir: Path | None = None) -> Path:
    return (config_dir or _CONFIG_DIR) / f"show_bible.{show_id}.json"


def load(show_id: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load the show bible for *show_id*."""
    path = bible_path(show_id, config_dir)
    if not path.exists():
        raise FileNotFoundError(f"show bible not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def default_caption_policy(bible: dict[str, Any]) -> dict[str, Any]:
    cp = bible.get("caption_policy") or {}
    return {
        "burn_in": cp.get("burn_in", "broll_only"),
        "sidecar": bool(cp.get("sidecar", True)),
    }


def default_brain(bible: dict[str, Any]) -> str:
    return str(bible.get("default_brain", "halt"))


def default_formats(bible: dict[str, Any]) -> list[str]:
    fmts = bible.get("default_formats") or ["horizontal"]
    return list(fmts)


def thresholds(bible: dict[str, Any]) -> dict[str, Any]:
    return bible.get("thresholds", {})


def voice(bible: dict[str, Any]) -> dict[str, Any]:
    """Voice config: {engine, reference_audio, reference_text}.

    The reference clip pins one consistent cloned voice so every synth sounds
    like the same human — set once here rather than via a per-run env var.
    """
    return bible.get("voice", {}) or {}

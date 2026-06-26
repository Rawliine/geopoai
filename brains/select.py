"""Resolve a brain implementation by name."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .api import make_api_brain
from .base import Brain
from .cli_agent import make_cli_brain
from .halt import HaltBrain

_PACKAGE_DEFAULTS = Path(__file__).resolve().parent / "brains.json"
_REPO_DEFAULTS = Path(__file__).resolve().parent.parent / "config" / "brains.json"

_KNOWN_BRAINS = frozenset({"halt", "claude-cli", "gemini-cli", "api"})


def _load_defaults() -> dict[str, Any]:
    for path in (_REPO_DEFAULTS, _PACKAGE_DEFAULTS):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def select_brain(name: str, cfg: dict[str, Any] | None = None) -> Brain:
    """Return a brain instance for ``halt | claude-cli | gemini-cli | api``."""
    normalized = name.strip().lower()
    if normalized not in _KNOWN_BRAINS:
        raise ValueError(f"unknown brain {name!r}; expected one of {sorted(_KNOWN_BRAINS)}")

    defaults = _load_defaults()
    merged: dict[str, Any] = {**defaults.get(normalized, {}), **(cfg or {})}

    if normalized == "halt":
        return HaltBrain()

    if normalized == "claude-cli":
        return make_cli_brain(
            merged.get("command_key", "claude_cli"),
            command_template=merged.get("command_template"),
            timeout=float(merged.get("timeout", 180)),
        )

    if normalized == "gemini-cli":
        return make_cli_brain(
            merged.get("command_key", "gemini_cli"),
            command_template=merged.get("command_template"),
            timeout=float(merged.get("timeout", 180)),
        )

    return make_api_brain(
        provider=merged.get("provider"),
        model=merged.get("model"),
        temperature=float(merged.get("temperature", 0)),
        max_repairs=int(merged.get("max_repairs", 2)),
    )

"""Cached loader for config/design_tokens.json — single source of brand truth."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOKENS_PATH = _REPO_ROOT / "config" / "design_tokens.json"


@lru_cache(maxsize=1)
def load_tokens() -> dict[str, Any]:
    """Return the parsed design-tokens document (cached for process lifetime)."""
    if not _TOKENS_PATH.is_file():
        raise FileNotFoundError(f"design tokens not found: {_TOKENS_PATH}")
    return json.loads(_TOKENS_PATH.read_text(encoding="utf-8"))


def tokens_path() -> Path:
    """Absolute path to the frozen tokens file."""
    return _TOKENS_PATH

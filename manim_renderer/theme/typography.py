"""Font families and per-format size scale."""

from __future__ import annotations

from typing import Any

_FONTS_FALLBACK = {
    "primary": "Inter",
    "display": "Barlow Condensed",
    "mono": "JetBrains Mono",
    "math": "STIX Two Math",
}

_FONT_SCALE_FALLBACK = {
    "horizontal": {"title": 64, "body": 36, "label": 28, "caption": 22},
    "vertical": {"title": 84, "body": 48, "label": 36, "caption": 28},
}


def _load_typography_from_tokens() -> tuple[dict[str, str], dict[str, dict[str, int]]] | None:
    try:
        from tools.tokens import load_tokens
    except ImportError:
        return None
    try:
        tokens: dict[str, Any] = load_tokens()
        typo = tokens["typography"]
    except (FileNotFoundError, KeyError, TypeError):
        return None

    fonts = {
        "primary": typo.get("primary", _FONTS_FALLBACK["primary"]),
        "display": typo.get("display", _FONTS_FALLBACK["display"]),
        "mono": typo.get("mono", _FONTS_FALLBACK["mono"]),
        "math": typo.get("math", _FONTS_FALLBACK["math"]),
    }
    scale = typo.get("scale", _FONT_SCALE_FALLBACK)
    return fonts, scale


_loaded = _load_typography_from_tokens()
if _loaded is not None:
    FONTS, FONT_SCALE = _loaded
else:
    FONTS = _FONTS_FALLBACK.copy()
    FONT_SCALE = {k: v.copy() for k, v in _FONT_SCALE_FALLBACK.items()}

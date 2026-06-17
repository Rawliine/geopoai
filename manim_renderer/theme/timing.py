"""Named timing slots. Raw floats are banned in component code."""

from __future__ import annotations

from typing import Any

TIMING = {
    "instant": 0.0,
    "snap": 0.15,
    "fast": 0.3,
    "normal": 0.6,
    "slow": 1.0,
    "dramatic": 1.6,
    "crawl": 3.0,
}

STAGGER = {
    "dense": 0.08,
    "normal": 0.15,
    "dramatic": 0.3,
}

_BEATS_FALLBACK = {
    "beat_min_s": 2.0,
    "beat_max_s": 4.0,
    "static_max_s": 2.5,
    "stagger_ms": 120,
    "exit_ratio": 0.6,
    "read_rate_cps": 15,
    "callout_min_s": 1.2,
}


def _load_beats_from_tokens() -> dict[str, float | int] | None:
    try:
        from tools.tokens import load_tokens
    except ImportError:
        return None
    try:
        tokens: dict[str, Any] = load_tokens()
        timing = tokens["timing"]
    except (FileNotFoundError, KeyError, TypeError):
        return None

    return {
        key: timing.get(key, _BEATS_FALLBACK[key])
        for key in _BEATS_FALLBACK
    }


_loaded = _load_beats_from_tokens()
BEATS = _loaded if _loaded is not None else _BEATS_FALLBACK.copy()

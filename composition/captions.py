"""Caption burn-in — W15 implements against layout + timing tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build(
    vo_wav: Path,
    words_json: Path | None,
    layout_jsons: list[Path],
    tokens: dict[str, Any],
    fmt: str,
) -> Path:
    """Build an ASS subtitle file from VO alignment and occupancy layouts.

    Args:
        vo_wav: Episode voice-over waveform.
        words_json: Optional forced-alignment output
            (``[{word, start, end, confidence}]``). When ``None``, ASR is
            deferred to W15's align tool.
        layout_jsons: Per-clip ``*.layout.json`` files shifted into episode
            time for occupancy-aware placement.
        tokens: Parsed design tokens (typography, safe_areas, timing).
        fmt: Target format — ``horizontal`` or ``vertical``.

    Returns:
        Path to the generated ``.ass`` caption file.

    Raises:
        NotImplementedError: Stub — implemented in W15.
    """
    raise NotImplementedError("composition.captions.build is implemented in W15")

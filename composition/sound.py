"""Sound pass — W16 implements against events + SFX palette."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build(
    events_jsons: list[Path],
    offsets: list[float],
    vo_wav: Path,
    tokens: dict[str, Any],
) -> Path:
    """Mix SFX cues from clip events into a single episode waveform.

    Args:
        events_jsons: Per-clip ``*.events.json`` files (validated against
            docs/contracts/events.schema.json).
        offsets: Clip start times in seconds, parallel to *events_jsons*.
        vo_wav: Episode voice-over — priority bus for ducking.
        tokens: Parsed design tokens (``sound.vo_duck_db``, ``sound.target_lufs``).

    Returns:
        Path to ``mix.wav`` (VO + SFX + bed).

    Raises:
        NotImplementedError: Stub — implemented in W16.
    """
    raise NotImplementedError("composition.sound.build is implemented in W16")

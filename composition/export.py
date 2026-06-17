"""Per-platform export profiles — W17 implements."""

from __future__ import annotations

from typing import Any


def profiles(tokens: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return export profile definitions derived from design tokens.

    Args:
        tokens: Parsed design tokens (safe areas, typography scale, grading).

    Returns:
        Mapping of profile name (``yt_long``, ``shorts``) to encoder settings:
        resolution, fps, video codec, audio codec/bitrate, and caption policy.

    Raises:
        NotImplementedError: Stub — implemented in W17.
    """
    raise NotImplementedError("composition.export.profiles is implemented in W17")

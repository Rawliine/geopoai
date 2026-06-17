"""Clip boundary transitions — W17 implements."""

from __future__ import annotations

from typing import Any


def select_transition(
    outgoing_events: dict[str, Any] | None,
    incoming_events: dict[str, Any] | None,
    spec_transition: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the ffmpeg transition recipe for a clip boundary.

    Args:
        outgoing_events: Events document for the clip ending at the boundary.
        incoming_events: Events document for the clip starting after.
        spec_transition: Transition entry from compose.schema.json
            (``cut`` | ``crossfade`` | ``whoosh``).

    Returns:
        Normalized transition recipe for the assembly pass.

    Raises:
        NotImplementedError: Stub — implemented in W17.
    """
    raise NotImplementedError(
        "composition.transitions.select_transition is implemented in W17"
    )

"""Episode compose orchestrator — W17 implements against compose.schema.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def compose(compose_spec: dict[str, Any], workdir: Path) -> Path:
    """Assemble clips per *compose_spec* into a final episode MP4.

    Args:
        compose_spec: Validated compose document (clip order, transitions,
            audio inputs, export profile flags).
        workdir: Writable directory for intermediate artifacts (concat,
            caption burn, sound mix, grade passes).

    Returns:
        Path to the primary exported ``final_<profile>.mp4`` under *workdir*.

    Raises:
        NotImplementedError: Stub — implemented in W17.
    """
    raise NotImplementedError("composition.engine.compose is implemented in W17")

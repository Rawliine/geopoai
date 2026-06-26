"""Escape-hatch scene JSON contract — file path, class, and mandatory reason."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_MANIM_PKG = Path(__file__).resolve().parent.parent
_CUSTOM_SCENES = Path(__file__).resolve().parent / "custom_scenes"
_FILE_PATTERN = re.compile(
    r"^escape_hatch/custom_scenes/[A-Za-z0-9_\-]+\.py$"
)


@dataclass(frozen=True)
class EscapeHatchSpec:
    file: str
    class_name: str
    reason: str
    scene_path: Path


def parse_escape_hatch(scene: dict) -> EscapeHatchSpec:
    """Validate and resolve the ``escape_hatch`` block from a scene dict.

    Raises ``ValueError`` on any contract violation.
    """
    block = scene.get("escape_hatch")
    if not isinstance(block, dict):
        raise ValueError("escape_hatch: expected an object")

    file_ref = block.get("file")
    class_name = block.get("class")
    reason = block.get("reason")

    if not isinstance(file_ref, str) or not file_ref.strip():
        raise ValueError("escape_hatch.file: required non-empty string")
    if not isinstance(class_name, str) or not class_name.strip():
        raise ValueError("escape_hatch.class: required non-empty string")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("escape_hatch.reason: mandatory non-empty string")

    file_ref = file_ref.strip()
    class_name = class_name.strip()
    reason = reason.strip()

    if not _FILE_PATTERN.match(file_ref):
        raise ValueError(
            "escape_hatch.file: must match "
            "'escape_hatch/custom_scenes/<name>.py'"
        )

    scene_path = (_MANIM_PKG / file_ref).resolve()
    custom_root = _CUSTOM_SCENES.resolve()
    try:
        scene_path.relative_to(custom_root)
    except ValueError as exc:
        raise ValueError(
            "escape_hatch.file: custom scene files must live under custom_scenes/"
        ) from exc

    if not scene_path.is_file():
        raise ValueError(f"escape_hatch.file: not found: {file_ref}")

    return EscapeHatchSpec(
        file=file_ref,
        class_name=class_name,
        reason=reason,
        scene_path=scene_path,
    )

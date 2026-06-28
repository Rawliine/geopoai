"""Halt brain — operator-in-the-loop manual authoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import AwaitingBrainError, Brain


class HaltBrain:
    """Write instruction + schema to the stage dir and signal awaiting_brain."""

    name = "halt"

    def author(self, instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        stage_dir = context.get("stage_dir")
        if not stage_dir:
            raise ValueError("halt brain requires context['stage_dir']")

        root = Path(stage_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "instruction.md").write_text(instruction.strip() + "\n", encoding="utf-8")
        (root / "schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

        raise AwaitingBrainError(
            f"halt brain wrote instruction.md and schema.json to {root}; awaiting operator"
        )

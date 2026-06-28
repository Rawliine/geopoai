"""Shared stage-execution context.

Kept in its own module so both the runner and the individual stages can import
it without a cycle. `hooks` is the injection seam tests use to stub the heavy
renderer/compose calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class StageContext:
    repo_root: Path
    ep_dir: Path
    manifest: dict[str, Any]
    bible: dict[str, Any]
    brain_name: str
    brain_cfg: dict[str, Any] | None = None
    # Injection seam: tests/operators can stub the heavy calls.
    #   render_clip(scene: dict, clip_id: str, repo_root: Path) -> dict[str, str]
    #   run_compose(spec_path: Path, out_name: str, repo_root: Path) -> dict[str, str]
    hooks: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def stage_dir(self, stage: str) -> Path:
        return self.ep_dir / "stages" / stage

"""Stage registry.

Each stage module exposes a module-level `STAGE: Stage`. A brain stage provides
`build(ctx) -> (instruction, schema)`, `merge(manifest, artifact)`, and an
optional `check(ctx, artifact) -> list[str]` of extra validation errors. A
mechanical stage provides `execute(ctx)`. The runner drives them uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from orchestration.context import StageContext


@dataclass
class Stage:
    name: str
    is_brain: bool
    build: Callable[[StageContext], tuple[str, dict[str, Any]]] | None = None
    merge: Callable[[StageContext, dict[str, Any]], None] | None = None
    check: Callable[[StageContext, dict[str, Any]], list[str]] | None = None
    execute: Callable[[StageContext], None] | None = None


from orchestration.stages import (  # noqa: E402
    angle,
    compose,
    ingest,
    publish,
    qc,
    render,
    scenes,
    script,
    storyboard,
    voice,
)

# Sequence order matches manifest.STAGE_SEQUENCE.
# voice runs before storyboard: the measured VO is the master clock, so clip
# durations are derived from real audio timing rather than guessed by the brain.
_ORDERED = [
    ingest.STAGE,
    angle.STAGE,
    script.STAGE,
    voice.STAGE,
    storyboard.STAGE,
    scenes.STAGE,
    render.STAGE,
    compose.STAGE,
    qc.STAGE,
    publish.STAGE,
]

REGISTRY: dict[str, Stage] = {s.name: s for s in _ORDERED}


def get(name: str) -> Stage:
    if name not in REGISTRY:
        raise KeyError(f"unknown stage {name!r}")
    return REGISTRY[name]

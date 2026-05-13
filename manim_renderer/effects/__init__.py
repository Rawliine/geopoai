"""Effects subsystem: entrance/emphasis/exit/transition factories.

Public API:
  * `get_entrance(name, mobject, timing, **params) -> Animation`
  * `get_emphasis(name, mobject, timing, **params) -> Animation`
  * `get_exit(name, mobject, timing, **params) -> Animation`
  * `entrance_names()`, `emphasis_names()`, `exit_names()` for schema generation

`transitions` (scene-level) is reserved for Phase 2 — not implemented here.
"""

from manim_renderer.effects.entrances import (
    ENTRANCES,
    entrance_names,
    get_entrance,
)
from manim_renderer.effects.emphasis import (
    EMPHASIS,
    emphasis_names,
    get_emphasis,
)
from manim_renderer.effects.exits import EXITS, exit_names, get_exit
from manim_renderer.effects._spec import EffectSpec

__all__ = [
    "EffectSpec",
    "ENTRANCES",
    "EMPHASIS",
    "EXITS",
    "get_entrance",
    "get_emphasis",
    "get_exit",
    "entrance_names",
    "emphasis_names",
    "exit_names",
]

"""Action dispatch registries.

Two registries with distinct semantics:

  * `COMPONENT_REGISTRY: dict[str, type[BaseComponent]]`
        Action name -> component class. The runner instantiates a new mobject,
        optionally positions it via slot/anchor, registers it by id, and plays
        its entrance animation.

  * `ACTION_REGISTRY: dict[str, Callable[[ActionContext], Animation | None]]`
        Action name -> callable that mutates or removes existing mobjects. No
        new mobject is created; no id is registered. Phase 2 camera actions
        (`cameraZoom`/`cameraPan`/`cameraFocus`) plug in here.

`scene.py` dispatches on which registry an action name lives in.
`REGISTRY` is kept as a back-compat alias for `COMPONENT_REGISTRY` — no current
caller uses it but it documents the migration.
"""

from __future__ import annotations

from typing import Callable, Optional

from manim import Animation

from manim_renderer.actions import ActionContext, remove_component
from manim_renderer.components.text_card import TextCard

COMPONENT_REGISTRY: dict = {
    "showTextCard": TextCard,
}

ACTION_REGISTRY: dict[str, Callable[[ActionContext], Optional[Animation]]] = {
    "removeComponent": remove_component,
}

# Back-compat alias — same dict identity. Will be removed once nothing imports it.
REGISTRY = COMPONENT_REGISTRY

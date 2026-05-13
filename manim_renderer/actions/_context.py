"""ActionContext — argument bundle passed to every ACTION_REGISTRY callable.

Action callables have the shape:
    (ctx: ActionContext) -> Animation | None

They mutate or remove existing scene mobjects. They do NOT instantiate new
components — that's the COMPONENT_REGISTRY's job. Phase 2's camera actions
plug into this same shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from manim import MovingCameraScene


@dataclass
class ActionContext:
    params: dict
    id_to_mobject: dict[str, Any]
    format: str
    scene: "MovingCameraScene"  # access to camera, etc. (Phase 2 uses this)

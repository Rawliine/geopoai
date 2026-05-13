"""Action callables — mutate or remove existing scene mobjects.

Distinct from `components/` (which create new mobjects). Each action takes an
`ActionContext` and returns an `Animation` (most), or `None` (instant state
changes — none in Phase 1).

Phase 1 actions:
  * `removeComponent` — fade/dissolve an existing component out.

Phase 2 will add:
  * `cameraZoom`, `cameraPan`, `cameraFocus`
  * PayoffMatrix mutations move here from PR 1.5: `highlightCell`, `crossOut`,
    `bestResponseArrow`.
"""

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.remove_component import remove_component

__all__ = ["ActionContext", "remove_component"]

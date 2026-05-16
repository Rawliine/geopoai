"""Action callables — mutate or remove existing scene mobjects.

Distinct from `components/` (which create new mobjects). Each action takes an
`ActionContext` and returns an `Animation` (most), or `None` (instant state
changes — none in Phase 1).

Phase 1 actions:
  * `removeComponent`    — fade/dissolve an existing component out.
  * `highlightCell`      — colored overlay on a PayoffMatrix cell.
  * `crossOut`           — strikethrough a PayoffMatrix row or column.
  * `bestResponseArrow`  — arrow between two PayoffMatrix cells, actor-colored.

Phase 2 actions:
  * `setRole`     — record a new role for an existing component;
    becomes the trigger for restage in PR G.

Phase 2 will further add:
  * `cameraZoom`, `cameraPan`, `cameraFocus` (Phase 3 per plan.md).
"""

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.best_response_arrow import best_response_arrow
from manim_renderer.actions.cross_out import cross_out
from manim_renderer.actions.highlight_cell import highlight_cell
from manim_renderer.actions.remove_component import remove_component
from manim_renderer.actions.set_layout import set_layout
from manim_renderer.actions.set_role import set_role

__all__ = [
    "ActionContext",
    "remove_component",
    "highlight_cell",
    "cross_out",
    "best_response_arrow",
    "set_layout",
    "set_role",
]

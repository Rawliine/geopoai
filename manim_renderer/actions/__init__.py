"""Action callables — mutate or remove existing scene mobjects.

Distinct from `components/` (which create new mobjects). Each action takes an
`ActionContext` and returns an `Animation` (most), or `None` (instant state
changes — none in Phase 1).

Phase 1 actions:
  * `removeComponent`    — fade/dissolve an existing component out.
  * `highlightCell`      — colored overlay on a PayoffMatrix cell.
  * `crossOut`           — strikethrough a PayoffMatrix row or column.
  * `bestResponseArrow`  — arrow between two PayoffMatrix cells, actor-colored.

Phase 2 will add:
  * `cameraZoom`, `cameraPan`, `cameraFocus`
  * Removable highlight overlays (highlights currently can't be undone — they
    have no id since they're ephemeral by design).
"""

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.best_response_arrow import best_response_arrow
from manim_renderer.actions.cross_out import cross_out
from manim_renderer.actions.highlight_cell import highlight_cell
from manim_renderer.actions.remove_component import remove_component

__all__ = [
    "ActionContext",
    "remove_component",
    "highlight_cell",
    "cross_out",
    "best_response_arrow",
]

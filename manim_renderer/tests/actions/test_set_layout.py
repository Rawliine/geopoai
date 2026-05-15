"""PR W — `setLayout` swaps the scene's layout in place.

The callable resolves the new layout against the scene's format,
assigns `scene._layout`, and remaps slot bindings whose slot names
disappear on the new layout. Restage (in `_RESTAGE_AFTER_ACTIONS`)
animates the cast into the new positions.
"""

from __future__ import annotations

from manim_renderer.actions._context import ActionContext
from manim_renderer.actions.set_layout import set_layout
from manim_renderer.layouts.resolver import resolve_layout


class _StubScene:
    def __init__(self, layout_name: str, fmt: str = "horizontal"):
        self._format = fmt
        self._layout = resolve_layout(layout_name, fmt)
        self._id_to_slot: dict[str, str | None] = {}
        self._id_to_mobject: dict = {}


def test_set_layout_swaps_active_layout():
    scene = _StubScene("title-body", "horizontal")
    ctx = ActionContext(
        params={"layout": "split"},
        id_to_mobject={}, format="horizontal", scene=scene,
    )
    set_layout(ctx)
    assert scene._layout.name == "split"


def test_set_layout_remaps_orphan_slot_bindings():
    """title-body → split should migrate `body` → `left`."""
    scene = _StubScene("title-body", "horizontal")
    scene._id_to_slot = {"hero": "body", "side": "title"}
    ctx = ActionContext(
        params={"layout": "split"},
        id_to_mobject={}, format="horizontal", scene=scene,
    )
    set_layout(ctx)
    # `body` migrates to `left`; `title` has no migration entry so
    # falls back to the first slot of split (alphabetical: `left`).
    assert scene._id_to_slot["hero"] == "left"
    assert scene._id_to_slot["side"] == "left"


def test_set_layout_rejects_incompatible_format():
    """split is horizontal-only; trying to apply it in vertical raises."""
    scene = _StubScene("hero", "vertical")
    ctx = ActionContext(
        params={"layout": "split"},
        id_to_mobject={}, format="vertical", scene=scene,
    )
    try:
        set_layout(ctx)
    except ValueError:
        return
    raise AssertionError("expected ValueError for incompatible format")


def test_set_layout_no_op_when_scene_missing():
    """Unit-test path: action survives ctx.scene=None."""
    ctx = ActionContext(
        params={"layout": "split"},
        id_to_mobject={}, format="horizontal", scene=None,
    )
    assert set_layout(ctx) is None

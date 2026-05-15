"""setLayout action — swap the scene's layout mid-flight.

Each scene starts with one layout (from `scene.layout` in the JSON). Once
the runner enters its event loop the layout is locked — every show event
binds to a slot of the active layout. `setLayout` breaks that lock: it
resolves a new compatible layout and replaces `scene._layout`. The
post-action restage hook then asks the new layout to solve the live cast,
producing a fluid Transform from the old slot rects to the new ones.

JSON shape:
    { "at": 30.0, "action": "setLayout",
      "params": { "layout": "split", "timing": "normal" } }

Slot bindings:
  When a layout changes, slot names in `_id_to_slot` may no longer exist
  on the new layout (e.g. `body` from `title-body` is undefined under
  `trio`). For each such orphan we try a small migration map; failing
  that the component falls back to a free slot or — if none is
  reasonable — keeps its current position via the restage identity path.

The new layout must support the scene's format (e.g. `split` is
horizontal-only; trying to swap to it in a vertical scene raises
ValueError). The validator catches the same case at compose-time via the
LAYOUT_FORMATS table.
"""

from __future__ import annotations

from typing import Optional

from manim import Animation

from manim_renderer.actions._context import ActionContext
from manim_renderer.layouts.resolver import resolve_layout


# Static migration map for "old slot name → new slot name" when the
# author swaps layouts. Keyed by (old_layout, new_layout). Falls back to
# the first slot on the new layout (typically `main`/`body`/`top`).
_SLOT_MIGRATION: dict[tuple[str, str], dict[str, str]] = {
    ("title-body", "hero"): {"title": "main", "body": "main"},
    ("title-body", "split"): {"body": "left"},
    ("title-body", "stacked"): {"body": "top"},
    ("title-body", "trio"): {"body": "A"},
    ("title-body", "trio-stack"): {"body": "A"},
    ("title-body", "data-left"): {"body": "body"},
    ("title-body", "data-top"): {"body": "body"},
    ("hero", "title-body"): {"main": "body"},
    ("hero", "split"): {"main": "left"},
    ("hero", "stacked"): {"main": "top"},
    ("hero", "trio"): {"main": "A"},
    ("hero", "trio-stack"): {"main": "A"},
    ("hero", "data-left"): {"main": "body"},
    ("hero", "data-top"): {"main": "body"},
    ("split", "title-body"): {"left": "body", "right": "body"},
    ("split", "hero"): {"left": "main", "right": "main"},
    ("split", "trio"): {"left": "A", "right": "C"},
    ("stacked", "title-body"): {"top": "title", "bottom": "body"},
    ("stacked", "hero"): {"top": "main", "bottom": "main"},
    ("stacked", "trio-stack"): {"top": "A", "bottom": "C"},
    ("data-left", "title-body"): {"data": "body", "body": "body"},
    ("data-left", "split"): {"data": "left", "body": "right"},
    ("data-top", "title-body"): {"data": "body", "body": "body"},
    ("data-top", "stacked"): {"data": "top", "body": "bottom"},
    ("trio", "split"): {"A": "left", "B": "left", "C": "right"},
    ("trio", "hero"): {"A": "main", "B": "main", "C": "main"},
    ("trio-stack", "stacked"): {"A": "top", "B": "top", "C": "bottom"},
    ("trio-stack", "hero"): {"A": "main", "B": "main", "C": "main"},
}


def set_layout(ctx: ActionContext) -> Optional[Animation]:
    new_name = ctx.params.get("layout")
    if not new_name:
        raise ValueError("setLayout requires params.layout")
    scene = ctx.scene
    if scene is None:
        # Unit-test path: nothing to swap, no animation produced.
        return None

    fmt = getattr(scene, "_format", ctx.format)
    new_layout = resolve_layout(new_name, fmt)
    old_layout = getattr(scene, "_layout", None)
    old_name = getattr(old_layout, "name", "") if old_layout else ""

    scene._layout = new_layout

    # Remap slot bindings. Components whose slot vanishes on the new
    # layout migrate per `_SLOT_MIGRATION`; orphans drop to None so the
    # solver leaves them in place (next restage may pick them up if a
    # showCalloutBox or setRole event reassigns them).
    migration = _SLOT_MIGRATION.get((old_name, new_name), {})
    fallback = (sorted(new_layout.slots)[0] if new_layout.slots else None)

    slot_map = getattr(scene, "_id_to_slot", None)
    if slot_map is not None:
        for ident, slot in list(slot_map.items()):
            if slot is None:
                continue
            if slot in new_layout.slots:
                continue  # slot name carried over verbatim
            new_slot = migration.get(slot, fallback)
            slot_map[ident] = new_slot

    # The restage hook fires immediately after setLayout returns (added
    # to `_RESTAGE_AFTER_ACTIONS`), so we don't produce an animation
    # ourselves — the restage Transform IS the layout-swap animation.
    return None

"""Generic flex solver ().

Pure-math allocator: given a cast of `(id, role, preferred_size)` triples,
distribute them along `direction` inside `container`. If the cast's
preferred sum exceeds the container along the main axis, proportionally
shrink everything until it fits (then re-clamp to `MIN_DIM` so nothing
collapses to invisibility).

Used by every Phase 2 layout solver via `Layout.solve(...)` (PR J+).

Algorithm:
  1. Compute the total preferred extent along the main axis plus the gaps
     between items.
  2. If overflow, scale every entry's main-axis size proportionally so
     total + gaps == container_main. Cross-axis size shrinks by the same
     ratio (preserves aspect).
  3. Lay entries out sequentially with running offset, applying `align`
     for any leftover space on the main axis.
  4. Center each entry on the cross axis.

Empty cast → empty dict. `hidden` entries are dropped before allocation —
the runner is responsible for not adding `hidden` mobjects to the scene.
"""

from __future__ import annotations

from typing import Iterable, Literal

from manim_renderer.layouts.base import Rect


# Lower bound on any allocated dimension. Prevents pathological shrink-to-
# zero when the container is far too small for the cast. The validator's
# composition-fit tier catches these cases earlier; this is the
# runtime safety net.
MIN_DIM = 0.2


CastEntry = tuple[str, str, tuple[float, float]]


def flex_solve(
    cast: Iterable[CastEntry],
    *,
    container: Rect,
    direction: Literal["horizontal", "vertical"],
    gap: float = 0.5,
    align: Literal["center", "start", "end"] = "center",
) -> dict[str, Rect]:
    """Allocate `cast` along `direction` inside `container`.

    Args:
        cast: iterable of `(id, role, (preferred_w, preferred_h))`. Order
            in the cast = on-screen order.
        container: bounding `Rect` (scene coords) the cast fits inside.
        direction: `"horizontal"` lays entries left → right;
            `"vertical"` lays top → bottom.
        gap: spacing between adjacent entries (Manim units).
        align: how to distribute leftover main-axis space when the
            preferred extent is smaller than the container.

    Returns:
        Dict mapping each visible cast id → its allocated `Rect`.

    Notes:
      * `hidden` entries (preferred size `(0, 0)`) are filtered out — they
        do not consume space or get a Rect.
      * Empty cast returns `{}`.
      * Single visible entry always centers in the container (regardless
        of `align`).
    """
    visible: list[CastEntry] = [
        (id_, role, sz) for id_, role, sz in cast if sz[0] > 0 and sz[1] > 0
    ]
    if not visible:
        return {}

    n = len(visible)
    horizontal = direction == "horizontal"

    if horizontal:
        container_main = container.width
        container_cross = container.height
        cont_main_center = container.cx
        cont_cross_center = container.cy
    else:
        container_main = container.height
        container_cross = container.width
        cont_main_center = container.cy
        cont_cross_center = container.cx

    # Preferred main-axis sums (without gap budget).
    if horizontal:
        pref_main = [w for _, _, (w, _h) in visible]
        pref_cross = [h for _, _, (_w, h) in visible]
    else:
        pref_main = [h for _, _, (_w, h) in visible]
        pref_cross = [w for _, _, (w, _h) in visible]

    total_gap = gap * max(0, n - 1)
    available_main = max(0.0, container_main - total_gap)
    sum_pref = sum(pref_main)

    if sum_pref <= 0:
        return {}

    if sum_pref > available_main:
        scale = available_main / sum_pref
    else:
        scale = 1.0

    # Apply scale + clamp to MIN_DIM (preserves visibility on extreme shrink).
    alloc_main = [max(MIN_DIM, m * scale) for m in pref_main]
    alloc_cross = [
        max(MIN_DIM, min(container_cross, c * scale))
        for c in pref_cross
    ]

    used_main = sum(alloc_main) + total_gap
    slack = container_main - used_main

    # Cast order maps to on-screen order: horizontal → left-to-right (+x);
    # vertical → top-to-bottom (which is -y in Manim's y-up coord system).
    # `align` distributes leftover slack along the main axis.
    main_min = cont_main_center - container_main / 2.0  # left/bottom edge
    main_max = cont_main_center + container_main / 2.0  # right/top edge

    if align == "start":
        # cast[0] hugs the start edge (left for horizontal, top for vertical).
        cursor = main_min if horizontal else main_max
    elif align == "end":
        cursor = (main_min + slack) if horizontal else (main_max - slack)
    else:  # center
        cursor = (
            (main_min + slack / 2.0) if horizontal else (main_max - slack / 2.0)
        )

    out: dict[str, Rect] = {}
    for (id_, _role, _pref), w_main, w_cross in zip(visible, alloc_main, alloc_cross):
        if horizontal:
            center_main = cursor + w_main / 2.0
            rect = Rect(
                cx=center_main,
                cy=cont_cross_center,
                width=w_main,
                height=w_cross,
            )
            cursor += w_main + gap
        else:
            # Cursor walks downward in y (top → bottom).
            center_main = cursor - w_main / 2.0
            rect = Rect(
                cx=cont_cross_center,
                cy=center_main,
                width=w_cross,
                height=w_main,
            )
            cursor -= w_main + gap
        out[id_] = rect

    return out

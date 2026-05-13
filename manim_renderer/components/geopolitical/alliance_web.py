"""AllianceWeb — nodes + edges showing alliance / rivalry / neutral relations.

Phase 1 simplification: **deterministic circular layout** rather than
force-directed. For typical node counts (3–10), evenly-spaced nodes on a
circle read cleaner and never produce overlapping pathological layouts. The
`seed` param rotates the whole ring by `2π × (seed mod 360) / 360` so the
same JSON renders identically across runs but different scenes can have
visually distinct orientations.

Force-directed is a Phase 2+ upgrade and lives in the handoff.md punch-list.

Edge styling by kind:
  * `alliance` — `positive` color, solid line
  * `rivalry`  — `negative` color, dashed line
  * `neutral`  — `neutral` color, thin line

Custom anchors:
  * `node:<id>` — that node's center

```json
{
  "action": "showAllianceWeb",
  "params": {
    "id": "web",
    "nodes": [
      {"id": "usa", "label": "USA", "color": "actor_a"},
      {"id": "rus", "label": "Russia", "color": "actor_b"},
      {"id": "chn", "label": "China", "color": "actor_c"}
    ],
    "edges": [
      {"from": "usa", "to": "rus", "kind": "rivalry"},
      {"from": "rus", "to": "chn", "kind": "alliance"}
    ],
    "size": "medium",
    "seed": 42,
    "effect": "level-by-level"
  }
}
```
"""

from __future__ import annotations

import math

import numpy as np
from manim import (
    Circle,
    DashedLine,
    FadeIn,
    LaggedStart,
    Line,
    ORIGIN,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.resolvers.size import resolve_size
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.timing import STAGGER, TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


_PALETTE = {**ACTORS, **SEMANTIC, **UI}

_NODE_RADIUS = 0.25
_EDGE_KINDS = {"alliance", "rivalry", "neutral"}
_EDGE_KIND_TO_COLOR = {
    "alliance": "positive",
    "rivalry":  "negative",
    "neutral":  "neutral",
}
_EDGE_STROKE = {"alliance": 3.0, "rivalry": 2.5, "neutral": 1.5}
_LABEL_BUFF = 0.05


def _resolve_color(key: str | None, fallback: str = "text_primary") -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


class AllianceWeb(BaseComponent):
    """Circular node arrangement with kind-colored edges."""

    def build(self) -> None:
        p = self.params

        nodes = p.get("nodes")
        if not nodes or not isinstance(nodes, list):
            raise ValueError("AllianceWeb requires non-empty params.nodes list")

        seen_ids: set[str] = set()
        for n in nodes:
            if "id" not in n:
                raise ValueError("AllianceWeb node missing required `id`")
            if n["id"] in seen_ids:
                raise ValueError(f"AllianceWeb duplicate node id {n['id']!r}")
            seen_ids.add(n["id"])

        self._node_ids: list[str] = [n["id"] for n in nodes]
        self._node_labels: list[str] = [str(n.get("label", n["id"])) for n in nodes]
        self._node_colors: list[str] = [
            _resolve_color(n.get("color"), fallback="text_accent") for n in nodes
        ]

        edges = p.get("edges") or []
        for e in edges:
            if "from" not in e or "to" not in e:
                raise ValueError("AllianceWeb edge requires `from` and `to`")
            if e["from"] not in seen_ids:
                raise ValueError(
                    f"AllianceWeb edge.from={e['from']!r} not in nodes"
                )
            if e["to"] not in seen_ids:
                raise ValueError(
                    f"AllianceWeb edge.to={e['to']!r} not in nodes"
                )
            kind = e.get("kind", "neutral")
            if kind not in _EDGE_KINDS:
                raise ValueError(
                    f"AllianceWeb edge.kind must be one of {sorted(_EDGE_KINDS)}; "
                    f"got {kind!r}"
                )

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="web")
        seed = int(p.get("seed", 0))

        # Lay out nodes on a circle (deterministic).
        n = len(self._node_ids)
        radius = min(width, height) / 2 * 0.72
        rotation_rad = (seed % 360) * math.pi / 180.0
        # In vertical, rotate by 90° so the natural top-of-circle node lands
        # at the top (rather than at right, which is the math convention).
        if self.format == "vertical":
            rotation_rad += math.pi / 2

        self._positions: dict[str, np.ndarray] = {}
        for i, node_id in enumerate(self._node_ids):
            theta = rotation_rad + 2 * math.pi * i / n
            self._positions[node_id] = np.array([
                radius * math.cos(theta),
                radius * math.sin(theta),
                0.0,
            ])

        # Build edges first (back layer), then nodes (front).
        self._edge_layer = VGroup()
        self._edge_mobs: list = []
        for e in edges:
            kind = e.get("kind", "neutral")
            color = _PALETTE[_EDGE_KIND_TO_COLOR[kind]]
            start = self._positions[e["from"]]
            end = self._positions[e["to"]]
            if kind == "rivalry":
                edge_mob = DashedLine(
                    start=start, end=end,
                    color=color,
                    stroke_width=_EDGE_STROKE[kind],
                )
            else:
                edge_mob = Line(
                    start=start, end=end,
                    color=color,
                    stroke_width=_EDGE_STROKE[kind],
                )
            self._edge_layer.add(edge_mob)
            self._edge_mobs.append(edge_mob)
        self.add(self._edge_layer)

        # Build node groups (circle + label).
        self._node_mobs: dict[str, Circle] = {}
        self._node_groups: dict[str, VGroup] = {}
        label_font_size = int(FONT_SCALE[self.format]["caption"] * 0.85)

        for node_id, label_text, hex_color in zip(
            self._node_ids, self._node_labels, self._node_colors
        ):
            pos = self._positions[node_id]
            circle = Circle(
                radius=_NODE_RADIUS,
                color=hex_color,
                fill_color=hex_color,
                fill_opacity=0.4,
                stroke_width=2.5,
            )
            circle.move_to(pos)
            label = Text(
                label_text,
                font=FONTS["primary"],
                font_size=label_font_size,
                color=UI["text_primary"],
            )
            # Label placed outward (away from center) so it never overlaps
            # the node circle. Direction = normalized position vector.
            norm = np.linalg.norm(pos)
            if norm < 1e-6:
                direction = np.array([0, -1, 0])
            else:
                direction = pos / norm
            label.move_to(
                pos + direction * (_NODE_RADIUS + _LABEL_BUFF + label.height / 2)
            )
            self._node_mobs[node_id] = circle
            self._node_groups[node_id] = VGroup(circle, label)
            self.add(self._node_groups[node_id])

        self.move_to(ORIGIN)

    # --- child id registration ----------------------------------------------

    def extra_id_registrations(self) -> dict:
        """Expose each node id as a top-level anchor target (`below:usa` etc.).

        Must stay in sync with `schema/validator.py:_ids_from_alliance_web`.
        """
        return dict(self._node_mobs)

    # --- bespoke entrance ---------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "level-by-level":
            # Nodes fade in first (staggered), then edges fade in together.
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])
            from manim import AnimationGroup, Succession
            node_anims = LaggedStart(
                *(FadeIn(g) for g in self._node_groups.values()),
                lag_ratio=lag,
                run_time=run_time,
            )
            if self._edge_mobs:
                edge_anim = FadeIn(self._edge_layer, run_time=run_time * 0.6)
                return Succession(node_anims, edge_anim)
            return node_anims
        return super().entrance(effect, timing, **extra)

    # --- custom anchors -----------------------------------------------------

    def _get_anchor_node(self, arg: str) -> np.ndarray:
        """`node:<id>` -> that node's center."""
        if arg not in self._node_mobs:
            raise KeyError(
                f"AllianceWeb has no node {arg!r}; "
                f"available: {sorted(self._node_mobs)}"
            )
        return self._node_mobs[arg].get_center()

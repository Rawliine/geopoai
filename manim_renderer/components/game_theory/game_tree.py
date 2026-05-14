"""GameTree — recursive layered tree of decision/outcome nodes.

Format-aware (per recap.md §7 LOCKED, single component):
  * horizontal → root on the LEFT, grows L→R (uses 16:9 width well)
  * vertical   → root on TOP, grows T→B (uses 9:16 height well), depth-capped

Layout algorithm (Reingold-Tilford-lite):
  * Leaves are placed evenly along the cross-axis.
  * Internal nodes center above (or beside) their children at the midpoint
    of their children's positions.
  * Levels are evenly spaced along the depth-axis.

Edge labels (`edge` field on a child node) are rendered along the connecting
line at its midpoint.

Custom anchors:
  * `node:<path>` — path is dot-separated indices from the root.
        `node:root`     -> root node center
        `node:root.0`   -> root's first child
        `node:root.1.0` -> root's second child's first child
    Numeric path components are 0-based indices into `children`.

```json
{
  "action": "showGameTree",
  "params": {
    "id": "tree",
    "nodes": {
      "label": "P1",
      "children": [
        {"label": "Cooperate", "edge": "C", "children": [
          {"label": "P2", "children": [
            {"label": "(3,3)", "edge": "C"},
            {"label": "(0,5)", "edge": "D"}
          ]}
        ]},
        {"label": "Defect", "edge": "D", "children": [
          {"label": "P2", "children": [
            {"label": "(5,0)", "edge": "C"},
            {"label": "(1,1)", "edge": "D"}
          ]}
        ]}
      ]
    },
    "size": "large",
    "timing": "normal",
    "effect": "level-by-level"
  }
}
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from manim import (
    Circle,
    Dot,
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

_NODE_RADIUS = 0.18
_EDGE_STROKE = 2.0
_LABEL_BUFF = 0.08
_VERTICAL_MAX_DEPTH_DEFAULT = 4


def _resolve_color(key: str | None, fallback: str = "text_primary") -> str:
    if key is None:
        return _PALETTE[fallback]
    if key not in _PALETTE:
        raise ValueError(
            f"unknown palette key {key!r}; available: {sorted(_PALETTE)}"
        )
    return _PALETTE[key]


@dataclass
class _TreeNode:
    """Internal representation of a tree node post-parse.

    Layout writes `pos` and `level` in a second pass.
    """
    label: str
    edge_label: str | None
    color: str
    children: list["_TreeNode"] = field(default_factory=list)
    pos: np.ndarray | None = None
    level: int = 0
    path: str = ""


def _parse_node(d: dict, color: str | None = None) -> _TreeNode:
    if "label" not in d:
        raise ValueError("GameTree node must have a `label`")
    node_color = _resolve_color(d.get("color", color))
    return _TreeNode(
        label=str(d["label"]),
        edge_label=d.get("edge"),
        color=node_color,
        children=[_parse_node(c, color=color) for c in d.get("children", [])],
    )


def _assign_paths(node: _TreeNode, path: str = "root") -> None:
    node.path = path
    for i, c in enumerate(node.children):
        _assign_paths(c, f"{path}.{i}")


def _truncate_depth(node: _TreeNode, max_depth: int, level: int = 0) -> None:
    """In-place: drop children past `max_depth`.

    `max_depth` is the number of levels visible (NOT the deepest level
    number). max_depth=3 renders levels 0, 1, 2 — so a node at level 2
    keeps its label but has its children dropped.
    """
    node.level = level
    if level >= max_depth - 1:
        node.children = []
        return
    for c in node.children:
        _truncate_depth(c, max_depth, level + 1)


def _count_leaves(node: _TreeNode) -> int:
    if not node.children:
        return 1
    return sum(_count_leaves(c) for c in node.children)


def _max_depth(node: _TreeNode) -> int:
    if not node.children:
        return 1
    return 1 + max(_max_depth(c) for c in node.children)


def _layout_horizontal(
    node: _TreeNode,
    *,
    x_left: float,
    x_right: float,
    y_top: float,
    y_bottom: float,
) -> None:
    """Place nodes so root is at left, leaves at right. Leaves spread evenly
    along the y-axis; parents centered between their children."""
    max_d = _max_depth(node)
    leaf_count = _count_leaves(node)
    x_step = (x_right - x_left) / max(max_d - 1, 1)

    # Leaf y-positions: evenly spaced from top to bottom.
    if leaf_count == 1:
        leaf_ys = [(y_top + y_bottom) / 2]
    else:
        leaf_ys = list(np.linspace(y_top, y_bottom, leaf_count))

    leaf_iter = iter(leaf_ys)

    def assign(n: _TreeNode, depth: int) -> float:
        x = x_left + depth * x_step
        if not n.children:
            y = next(leaf_iter)
        else:
            child_ys = [assign(c, depth + 1) for c in n.children]
            y = sum(child_ys) / len(child_ys)
        n.pos = np.array([x, y, 0.0])
        return y

    assign(node, 0)


def _layout_vertical(
    node: _TreeNode,
    *,
    x_left: float,
    x_right: float,
    y_top: float,
    y_bottom: float,
) -> None:
    """Root at top, leaves at bottom. Leaves spread evenly along x; parents
    centered between their children."""
    max_d = _max_depth(node)
    leaf_count = _count_leaves(node)
    y_step = (y_top - y_bottom) / max(max_d - 1, 1)

    if leaf_count == 1:
        leaf_xs = [(x_left + x_right) / 2]
    else:
        leaf_xs = list(np.linspace(x_left, x_right, leaf_count))

    leaf_iter = iter(leaf_xs)

    def assign(n: _TreeNode, depth: int) -> float:
        y = y_top - depth * y_step
        if not n.children:
            x = next(leaf_iter)
        else:
            child_xs = [assign(c, depth + 1) for c in n.children]
            x = sum(child_xs) / len(child_xs)
        n.pos = np.array([x, y, 0.0])
        return x

    assign(node, 0)


class GameTree(BaseComponent):
    """Recursive game tree, format-aware."""

    SIZE_KIND = "tree"

    def build(self) -> None:
        p = self.params

        nodes = p.get("nodes")
        if not nodes or not isinstance(nodes, dict):
            raise ValueError("GameTree requires non-empty params.nodes (object)")

        size_role = p.get("size", "medium")
        width, height = resolve_size(size_role, self.format, kind="tree")
        max_depth = int(p.get("max_depth", _VERTICAL_MAX_DEPTH_DEFAULT))

        # Parse + level assignment + (in vertical) depth cap.
        self._root = _parse_node(nodes)
        if self.format == "vertical":
            _truncate_depth(self._root, max_depth, level=0)
        else:
            _truncate_depth(self._root, _max_depth(self._root), level=0)
        _assign_paths(self._root)

        # Layout into local coords.
        margin = 0.06
        if self.format == "horizontal":
            _layout_horizontal(
                self._root,
                x_left=-width / 2 + width * margin,
                x_right=width / 2 - width * margin,
                y_top=height / 2 - height * margin,
                y_bottom=-height / 2 + height * margin,
            )
        else:
            _layout_vertical(
                self._root,
                x_left=-width / 2 + width * margin,
                x_right=width / 2 - width * margin,
                y_top=height / 2 - height * margin,
                y_bottom=-height / 2 + height * margin,
            )

        # Render: edges first (bottom layer), then node circles + labels on top.
        # Grouped by depth so level-by-level entrance can reveal them in order.
        self._path_to_mob: dict[str, VGroup] = {}
        self._depth_groups: dict[int, list[VGroup]] = {}
        self._max_level = 0

        label_font_size = int(FONT_SCALE[self.format]["caption"] * 0.85)
        edge_label_font_size = int(FONT_SCALE[self.format]["caption"] * 0.75)

        # First pass: build edges.
        self._edge_layer = VGroup()
        self.add(self._edge_layer)

        def render_edges(n: _TreeNode) -> None:
            for c in n.children:
                line = Line(
                    start=n.pos,
                    end=c.pos,
                    color=UI["border"],
                    stroke_width=_EDGE_STROKE,
                )
                self._edge_layer.add(line)
                if c.edge_label:
                    edge_label_mob = Text(
                        c.edge_label,
                        font=FONTS["primary"],
                        font_size=edge_label_font_size,
                        color=UI["text_secondary"],
                    )
                    mid = (n.pos + c.pos) / 2
                    edge_label_mob.move_to(mid)
                    self._edge_layer.add(edge_label_mob)
                render_edges(c)

        render_edges(self._root)

        # Second pass: build node groups (circle + label) per level.
        def render_nodes(n: _TreeNode) -> None:
            self._max_level = max(self._max_level, n.level)
            circle = Circle(
                radius=_NODE_RADIUS,
                color=n.color,
                fill_color=n.color,
                fill_opacity=0.25,
                stroke_width=2.0,
            )
            circle.move_to(n.pos)
            label = Text(
                n.label,
                font=FONTS["primary"],
                font_size=label_font_size,
                color=UI["text_primary"],
            )
            # Place label outside the node along the layout axis so internal
            # nodes don't get crowded by their own label.
            if self.format == "horizontal":
                label.next_to(circle, np.array([0, 1, 0]), buff=_LABEL_BUFF)
            else:
                label.next_to(circle, np.array([1, 0, 0]), buff=_LABEL_BUFF)
            group = VGroup(circle, label)
            self._path_to_mob[n.path] = group
            self._depth_groups.setdefault(n.level, []).append(group)
            self.add(group)
            for c in n.children:
                render_nodes(c)

        render_nodes(self._root)

        self.move_to(ORIGIN)

    # --- bespoke entrance ---------------------------------------------------

    def entrance(self, effect: str, timing: str, **extra):
        if effect == "level-by-level":
            run_time = TIMING[timing]
            lag = STAGGER.get(extra.get("stagger", "normal"), STAGGER["normal"])

            # Depth groups in order: edges fade in alongside the deeper level
            # they connect to (parent already visible by then).
            depth_anims = []
            for level in sorted(self._depth_groups):
                level_mobs = self._depth_groups[level]
                depth_anims.append(FadeIn(VGroup(*level_mobs)))
            edges_anim = FadeIn(self._edge_layer, run_time=run_time)
            lagged = LaggedStart(
                *depth_anims,
                lag_ratio=lag,
                run_time=run_time,
            )
            from manim import AnimationGroup
            return AnimationGroup(edges_anim, lagged)
        return super().entrance(effect, timing, **extra)

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_node(self, arg: str) -> np.ndarray:
        """`node:<path>` -> node center.

        Path syntax: `root`, `root.0`, `root.0.1`. Indices are 0-based into
        `children`. Bare `root` returns the root node.
        """
        if arg not in self._path_to_mob:
            raise KeyError(
                f"GameTree has no node at path {arg!r}; "
                f"available paths: {sorted(self._path_to_mob)}"
            )
        return self._path_to_mob[arg].get_center()

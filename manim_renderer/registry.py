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

from manim_renderer.actions import (
    ActionContext,
    best_response_arrow,
    cross_out,
    highlight_cell,
    remove_component,
    set_layout,
    set_role,
)
from manim_renderer.components.data_viz.bar_chart import BarChart
from manim_renderer.components.data_viz.line_chart import LineChart
from manim_renderer.components.data_viz.metric_group import MetricGroup
from manim_renderer.components.data_viz.stat_block import StatBlock
from manim_renderer.components.game_theory.game_tree import GameTree
from manim_renderer.components.game_theory.payoff_matrix import PayoffMatrix
from manim_renderer.components.geopolitical.alliance_web import AllianceWeb
from manim_renderer.components.narrative.callout_box import CalloutBox
from manim_renderer.components.narrative.icon import Icon
from manim_renderer.components.narrative.image_card import ImageCard
from manim_renderer.components.narrative.timeline import Timeline
from manim_renderer.components.text_card import TextCard

COMPONENT_REGISTRY: dict = {
    "showTextCard":      TextCard,
    "showStatBlock":     StatBlock,
    "showMetricGroup":   MetricGroup,
    "showCalloutBox":    CalloutBox,
    "showBarChart":      BarChart,
    "showLineChart":     LineChart,
    "showTimeline":      Timeline,
    "showGameTree":      GameTree,
    "showAllianceWeb":   AllianceWeb,
    "showPayoffMatrix":  PayoffMatrix,
    "showIcon":          Icon,
    "showImageCard":     ImageCard,
}

ACTION_REGISTRY: dict[str, Callable[[ActionContext], Optional[Animation]]] = {
    "removeComponent":     remove_component,
    "highlightCell":       highlight_cell,
    "crossOut":            cross_out,
    "bestResponseArrow":   best_response_arrow,
    "setLayout":           set_layout,
    "setRole":             set_role,
}

# Back-compat alias — same dict identity. Will be removed once nothing imports it.
REGISTRY = COMPONENT_REGISTRY

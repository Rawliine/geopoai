"""Bespoke incentive flywheel — circular feedback loop not in the component library."""

from __future__ import annotations

import math

import numpy as np
from manim import Circle, CurvedArrow, FadeIn, Text, VGroup

from manim_renderer.escape_hatch.base import EscapeHatchScene
from manim_renderer.theme.palette import SEMANTIC, UI
from manim_renderer.theme.timing import TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


class IncentiveFlywheelScene(EscapeHatchScene):
    def build(self) -> None:
        fmt = self._format
        title_size = FONT_SCALE[fmt]["title"]
        node_size = FONT_SCALE[fmt]["caption"]
        run_time = TIMING["normal"]

        title = Text(
            "Incentive Flywheel",
            font=FONTS["display"],
            font_size=title_size,
            color=UI["text_primary"],
        )
        title.to_edge(np.array([0.0, 1.0, 0.0]), buff=0.4)

        stages = [
            ("Invest", SEMANTIC["positive"]),
            ("Learn", SEMANTIC["highlight"]),
            ("Adapt", SEMANTIC["contested"]),
            ("Compound", SEMANTIC["positive"]),
        ]
        n = len(stages)
        radius = 2.2
        nodes = VGroup()
        positions: list[np.ndarray] = []

        for i, (label, color) in enumerate(stages):
            angle = 2 * math.pi * i / n + math.pi / 2
            pos = np.array([
                radius * math.cos(angle),
                radius * math.sin(angle),
                0.0,
            ])
            positions.append(pos)
            dot = Circle(radius=0.38, color=color, fill_opacity=0.9, stroke_color=UI["border"])
            dot.move_to(pos)
            txt = Text(
                label,
                font=FONTS["primary"],
                font_size=node_size,
                color=UI["text_primary"],
            )
            txt.move_to(pos + 0.55 * (pos / np.linalg.norm(pos[:2]) if np.linalg.norm(pos[:2]) else np.array([0, 1, 0])))
            nodes.add(dot, txt)

        arrows = VGroup()
        for i in range(n):
            p0 = positions[i]
            p1 = positions[(i + 1) % n]
            arrow = CurvedArrow(
                p0, p1,
                color=UI["text_secondary"],
                stroke_width=3,
                angle=-math.pi / 4,
            )
            arrows.add(arrow)

        hub = Text(
            "↻",
            font=FONTS["display"],
            font_size=title_size * 1.2,
            color=UI["text_accent"],
        )

        self.emit("insight", 0.6, id="flywheel-reveal")
        self.play(
            FadeIn(title, run_time=run_time * 0.6),
            FadeIn(nodes, run_time=run_time),
            FadeIn(arrows, run_time=run_time),
            FadeIn(hub, run_time=run_time * 0.8),
        )

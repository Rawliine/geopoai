"""TextCard — centered text. The Phase 0 smoke component.

Uses BaseComponent's default entrance/exit/anchor dispatch. Schema-allowed
effects for TextCard are constrained in `schema/action_schemas/show_text_card.json`
(currently only `fade-in`); the dispatch in BaseComponent will raise on anything
not in `effects.entrances.ENTRANCES` regardless.
"""

from __future__ import annotations

from manim import ORIGIN, Text

from manim_renderer.components.base import BaseComponent
from manim_renderer.theme.palette import UI
from manim_renderer.theme.typography import FONTS, FONT_SCALE


class TextCard(BaseComponent):
    def build(self) -> None:
        text = self.params.get("text", "")
        size_role = self.params.get("size", "title")
        font_size = FONT_SCALE[self.format][size_role]
        self.label = Text(
            text,
            font=FONTS["primary"],
            font_size=font_size,
            color=UI["text_primary"],
        )
        self.label.move_to(ORIGIN)
        self.add(self.label)

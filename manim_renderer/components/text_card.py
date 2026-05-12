"""TextCard — centered text that fades in. The Phase 0 smoke component."""

from manim import Text, FadeIn, FadeOut, ORIGIN

from manim_renderer.components.base import BaseComponent
from manim_renderer.theme.palette import UI
from manim_renderer.theme.timing import TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


class TextCard(BaseComponent):
    def build(self) -> None:
        text = self.params.get("text", "")
        size_role = self.params.get("size", "title")
        font_size = FONT_SCALE[self.format][size_role]
        # Manim's Text font_size is in pt-ish units; the FONT_SCALE values
        # are tuned for visible weight on screen.
        self.label = Text(
            text,
            font=FONTS["primary"],
            font_size=font_size,
            color=UI["text_primary"],
        )
        self.label.move_to(ORIGIN)
        self.add(self.label)

    def entrance(self, effect: str, timing: str):
        run_time = TIMING[timing]
        if effect == "fade-in" or effect is None:
            return FadeIn(self, run_time=run_time)
        raise ValueError(f"TextCard does not support entrance effect: {effect}")

    def exit(self, effect: str):
        run_time = TIMING.get("fast", 0.3)
        if effect == "fade-out" or effect is None:
            return FadeOut(self, run_time=run_time)
        raise ValueError(f"TextCard does not support exit effect: {effect}")

    def get_anchor(self, name: str):
        return self.label.get_center()

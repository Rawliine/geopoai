from manim import Text

from manim_renderer.escape_hatch.base import EscapeHatchScene
from manim_renderer.theme.palette import UI


class BadFontScene(EscapeHatchScene):
    def build(self) -> None:
        Text("leak", font="Inter", color=UI["text_primary"])

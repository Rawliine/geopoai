from manim import Circle

from manim_renderer.escape_hatch.base import EscapeHatchScene


class BadHexScene(EscapeHatchScene):
    def build(self) -> None:
        Circle(color="#ff0000")

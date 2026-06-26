import os

from manim_renderer.escape_hatch.base import EscapeHatchScene


class BadImportScene(EscapeHatchScene):
    def build(self) -> None:
        _ = os.getcwd()

"""Abstract base for all renderable components."""

from manim import VGroup


class BaseComponent(VGroup):
    def __init__(self, params: dict, format: str = "horizontal", **kwargs):
        super().__init__(**kwargs)
        self.params = params
        self.format = format
        self.id = params.get("id")
        self.build()

    def build(self) -> None:
        raise NotImplementedError

    def entrance(self, effect: str, timing: str):
        raise NotImplementedError

    def exit(self, effect: str):
        raise NotImplementedError

    def get_anchor(self, name: str):
        raise NotImplementedError

    def measure(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "center": self.get_center(),
        }

"""Action name → component class map."""

from manim_renderer.components.text_card import TextCard

REGISTRY: dict = {
    "showTextCard": TextCard,
}

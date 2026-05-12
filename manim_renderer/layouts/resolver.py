"""Layout lookup. Picks the right family by format, returns the named layout."""

from manim_renderer.layouts.base import Layout
from manim_renderer.layouts.horizontal import HORIZONTAL_LAYOUTS
from manim_renderer.layouts.vertical import VERTICAL_LAYOUTS

_FAMILIES: dict[str, dict[str, Layout]] = {
    "horizontal": HORIZONTAL_LAYOUTS,
    "vertical": VERTICAL_LAYOUTS,
}


def available_layouts(format: str) -> list[str]:
    family = _FAMILIES.get(format)
    return sorted(family.keys()) if family else []


def resolve_layout(name: str, format: str) -> Layout:
    family = _FAMILIES.get(format)
    if family is None:
        raise ValueError(f"unknown format {format!r}; expected 'horizontal' or 'vertical'")
    layout = family.get(name)
    if layout is None:
        raise ValueError(
            f"unknown layout {name!r} for format {format!r}; "
            f"available: {available_layouts(format)}"
        )
    return layout

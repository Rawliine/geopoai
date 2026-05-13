"""Abstract base for all renderable components.

Subclass contract:
  * `build()` — construct the static mobject tree. Called from `__init__`.
  * Optional override `entrance(effect, timing, **extra)` — bespoke entrance only;
    default dispatches to `effects.entrances.get_entrance`.
  * Optional override `exit(effect, timing, **extra)` — same shape for exits.
  * `_get_anchor_<token>(arg)` — implement custom anchor tokens (e.g. `cell:1,2`
    on PayoffMatrix becomes `_get_anchor_cell("1,2")`). Standard 9 names are
    provided by the base class.

Anchor name parsing (AGENT.md rule 9):
  `get_anchor("top")` -> `_get_anchor_top()`. Hyphens become underscores:
  `"top-left"` -> `_get_anchor_top_left()`. Tokens with arguments use
  `"<token>:<arg>"` -> `_get_anchor_<token>(arg)`. Subclasses with custom
  anchors must call `super().get_anchor(name)` for unknown names.
"""

from __future__ import annotations

import numpy as np
from manim import VGroup


class BaseComponent(VGroup):
    def __init__(self, params: dict, format: str = "horizontal", **kwargs):
        super().__init__(**kwargs)
        self.params = params
        self.format = format
        self.id = params.get("id")
        self.build()

    # --- contract for subclasses ---------------------------------------------

    def build(self) -> None:
        raise NotImplementedError

    # --- default entrance/exit dispatch via effects subsystem ---------------

    def entrance(self, effect: str, timing: str, **extra):
        from manim_renderer.effects.entrances import get_entrance
        return get_entrance(effect, self, timing, **extra)

    def exit(self, effect: str, timing: str = "fast", **extra):
        from manim_renderer.effects.exits import get_exit
        return get_exit(effect, self, timing, **extra)

    # --- anchor name parsing -------------------------------------------------

    def get_anchor(self, name: str) -> np.ndarray:
        token, sep, arg = name.partition(":")
        method_name = f"_get_anchor_{token.replace('-', '_')}"
        method = getattr(self, method_name, None)
        if method is None:
            raise KeyError(
                f"{type(self).__name__} has no anchor {name!r}; "
                f"available: {self._available_anchors()}"
            )
        return np.asarray(method(arg) if sep else method(), dtype=float)

    # Standard 9 anchor names — every component honors them out of the box.
    def _get_anchor_top(self): return self.get_top()
    def _get_anchor_bottom(self): return self.get_bottom()
    def _get_anchor_left(self): return self.get_left()
    def _get_anchor_right(self): return self.get_right()
    def _get_anchor_center(self): return self.get_center()
    def _get_anchor_top_left(self): return self.get_corner((-1, 1, 0))
    def _get_anchor_top_right(self): return self.get_corner((1, 1, 0))
    def _get_anchor_bottom_left(self): return self.get_corner((-1, -1, 0))
    def _get_anchor_bottom_right(self): return self.get_corner((1, -1, 0))

    def _available_anchors(self) -> list[str]:
        prefix = "_get_anchor_"
        return sorted(
            attr.removeprefix(prefix).replace("_", "-")
            for attr in dir(self)
            if attr.startswith(prefix) and callable(getattr(self, attr))
        )

    # --- bounds ---------------------------------------------------------------

    def measure(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "center": self.get_center(),
        }

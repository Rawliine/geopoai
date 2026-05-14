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

from manim_renderer.resolvers.size import resolve_size


class BaseComponent(VGroup):
    # Override in subclasses whose `resolve_size` kind differs from "default".
    # Consumed by the default `measure()` and by build() implementations.
    SIZE_KIND: str = "default"

    def __init__(self, params: dict, format: str = "horizontal", **kwargs):
        super().__init__(**kwargs)
        self.params = params
        self.format = format
        self.id = params.get("id")
        self.build()

    # --- contract for subclasses ---------------------------------------------

    def build(self) -> None:
        raise NotImplementedError

    # --- pre-build sizing estimator (used by validator + future solver) ------

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        """Return an estimated (width, height) in Manim units WITHOUT building
        the mobject.

        Pure-math estimator consumed by the validator's overflow checks (see
        `manim_renderer/schema/_dry_run.py`) and by the future layout solver.
        Must not construct Manim mobjects — that would defeat the point of the
        check (cheap, runs on every validate()).

        Default implementation reads `params.size` (default "medium") and the
        class's `SIZE_KIND` and looks up `resolve_size`. Subclasses with
        content-driven sizing (text-bearing components, group bundles) override
        this with their own estimator.
        """
        role = params.get("size", "medium")
        return resolve_size(role, format, kind=cls.SIZE_KIND)

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

    # --- child registration --------------------------------------------------

    def extra_id_registrations(self) -> dict:
        """Map of additional id -> mobject this component declares.

        Returns child-component ids that should be reachable as anchor targets
        from JSON (e.g. MetricGroup exposes its inner StatBlocks as `id1`,
        `id2`, ...). Default: no extras.

        The scene runner merges these into `id_to_mobject` after the parent
        has been registered. Collisions with already-registered ids fail the
        scene runner's duplicate-id assert (the validator should catch them
        first via the corresponding id_extractor — see schema/validator.py).
        """
        return {}

    # --- post-positioning hook -----------------------------------------------

    def position_finalized(
        self,
        *,
        anchor: str | None = None,
        target=None,
        format: str = "horizontal",
    ) -> None:
        """Hook called by the scene runner AFTER the component has been moved
        to its slot or anchor coord, AFTER its id has been registered, but
        BEFORE its entrance animation plays.

        Override for components that need to know either:
          * Their final on-screen position (e.g. to add a leader line whose
            endpoint depends on absolute coords), or
          * The mobject they were anchored against (CalloutBox, ConnectionLine,
            BadgeAnchor, etc.).

        Args:
            anchor: the anchor string the component was positioned with, or
                None if the component was placed in a slot or has no anchor.
            target: the mobject the anchor pointed at, if any. Already
                resolved against `id_to_mobject`. None if no anchor.
            format: scene format ("horizontal" | "vertical").

        Default: no-op.
        """
        return None


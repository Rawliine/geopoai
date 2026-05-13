"""Custom Animation classes used by effect factories.

Kept separate from `entrances.py` so the dispatch dict stays small and
readable. Each class here is a low-level Manim Animation subclass; effects
are a thin layer above that wires them into the EffectSpec system.
"""

from __future__ import annotations

from manim import Animation


class CountUpAnimation(Animation):
    """Interpolates a numeric mobject from `start_value` to `target_value`.

    The mobject must implement `set_value(value: float) -> None` — invoked on
    every frame with the interpolated value. StatBlock implements this
    directly; future numeric components must too. Manim's `DecimalNumber`
    already has this method, so it works there as well (when LaTeX is
    available).

    Why a custom Animation: Manim's `m.animate.set_value(x)` builds a
    transform that interpolates the mobject's data, which only makes sense
    for shape-mobjects. Numeric displays need to *re-render* on each frame
    using the interpolated value — this class does exactly that.
    """

    def __init__(
        self,
        mobject,
        *,
        start_value: float,
        target_value: float,
        run_time: float,
        **kwargs,
    ):
        super().__init__(mobject, run_time=run_time, **kwargs)
        # Manim's Mobject.__getattr__ synthesizes set_<attr>(value) setters for
        # any name. We need a *real* set_value defined directly on the class
        # (one that re-renders the display), so walk the MRO instead of
        # relying on hasattr.
        if not _class_defines(type(mobject), "set_value"):
            raise TypeError(
                f"CountUpAnimation requires {type(mobject).__name__} to define "
                f"set_value(value) as a real method, not Manim's synthesized "
                f"attribute setter. The implementation must re-render the "
                f"display each call."
            )
        self.start_value = float(start_value)
        self.target_value = float(target_value)

    def interpolate_mobject(self, alpha: float) -> None:
        # Manim's base interpolate_mobject iterates submobjects and calls
        # interpolate_submobject — that path can't re-render a numeric text
        # display. Override to drive the host's set_value(v) directly each
        # frame. When overriding interpolate_mobject (not the per-submobject
        # template), the Manim docs require manually applying rate_func.
        eased = self.rate_func(alpha)
        current = self.start_value + (self.target_value - self.start_value) * eased
        self.mobject.set_value(current)


def _class_defines(cls: type, name: str) -> bool:
    """True if `name` is defined directly anywhere in `cls`'s MRO."""
    return any(name in c.__dict__ for c in cls.__mro__)

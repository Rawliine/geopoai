"""Emphasis effects — applied to existing on-screen mobjects to draw attention.

Phase 1 ships `pulse` and `highlight`. Phase 2 adds the rest of the 8-effect
emphasis vocabulary (strike, glow, shake, surround, color-shift, dim-others).
"""

from __future__ import annotations

from manim import Animation, Indicate, Circumscribe

from manim_renderer.effects._spec import EffectSpec
from manim_renderer.theme.palette import SEMANTIC
from manim_renderer.theme.timing import TIMING


def _pulse(m, *, run_time, scale=1.15, color=None, **_):
    """Brief scale + color ping. `color` defaults to highlight yellow."""
    return Indicate(
        m,
        scale_factor=scale,
        color=color or SEMANTIC["highlight"],
        run_time=run_time,
    )


def _highlight(m, *, run_time, color=None, **_):
    """Surrounding rectangle traces around the target then fades."""
    return Circumscribe(
        m,
        color=color or SEMANTIC["highlight"],
        run_time=run_time,
    )


EMPHASIS: dict[str, EffectSpec] = {
    "pulse":     EffectSpec("pulse",     _pulse,     optional={"scale": 1.15, "color": None}),
    "highlight": EffectSpec("highlight", _highlight, optional={"color": None}),
}


def get_emphasis(name: str, mobject, timing: str, **extra) -> Animation:
    spec = EMPHASIS.get(name)
    if spec is None:
        raise KeyError(
            f"unknown emphasis effect {name!r}; available: {sorted(EMPHASIS)}"
        )
    if timing not in TIMING:
        raise KeyError(f"unknown timing {timing!r}; available: {sorted(TIMING)}")
    missing = [k for k in spec.required if k not in extra]
    if missing:
        raise KeyError(
            f"emphasis effect {name!r} missing required params: {missing}"
        )
    params = {**spec.optional, **extra}
    return spec.factory(mobject, run_time=TIMING[timing], **params)


def emphasis_names() -> list[str]:
    return sorted(EMPHASIS)

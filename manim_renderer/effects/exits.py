"""Exit effects.

Phase 1 ships `fade-out` and `dissolve`. Phase 2 adds the remaining 4 exits
(shrink, slide-out-left, slide-out-right, grey-out).
"""

from __future__ import annotations

from manim import Animation, FadeOut

from manim_renderer.effects._spec import EffectSpec
from manim_renderer.theme.timing import TIMING


def _fade_out(m, *, run_time, **_):
    return FadeOut(m, run_time=run_time)


def _dissolve(m, *, run_time, **_):
    # No first-class dissolve in Manim CE; FadeOut with longer run gives the
    # same visual read for now. Phase 2 may swap in a more textured exit.
    return FadeOut(m, run_time=run_time)


EXITS: dict[str, EffectSpec] = {
    "fade-out": EffectSpec("fade-out", _fade_out),
    "dissolve": EffectSpec("dissolve", _dissolve),
}


def get_exit(name: str, mobject, timing: str, **extra) -> Animation:
    spec = EXITS.get(name)
    if spec is None:
        raise KeyError(f"unknown exit effect {name!r}; available: {sorted(EXITS)}")
    if timing not in TIMING:
        raise KeyError(f"unknown timing {timing!r}; available: {sorted(TIMING)}")
    missing = [k for k in spec.required if k not in extra]
    if missing:
        raise KeyError(f"exit effect {name!r} missing required params: {missing}")
    params = {**spec.optional, **extra}
    return spec.factory(mobject, run_time=TIMING[timing], **params)


def exit_names() -> list[str]:
    return sorted(EXITS)

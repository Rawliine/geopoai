"""Entrance effects.

Each factory takes a mobject + run_time + per-effect params and returns a Manim
Animation. Callers go through `get_entrance(name, mobject, timing, **extra)`,
which validates required params and merges optional defaults.

Phase 1 ships a subset (~9) of the eventual 35-name vocabulary. New effects are
added by writing a factory + appending to `ENTRANCES`.
"""

from __future__ import annotations

from manim import (
    Animation,
    Create,
    FadeIn,
    GrowFromEdge,
    LaggedStart,
    Write,
    DOWN,
    LEFT,
    RIGHT,
    UP,
)

from manim_renderer.effects._animations import CountUpAnimation
from manim_renderer.effects._spec import EffectSpec
from manim_renderer.theme.timing import TIMING


# --- factories ---------------------------------------------------------------

def _fade_in(m, *, run_time, **_):
    return FadeIn(m, run_time=run_time)


def _write_in(m, *, run_time, **_):
    return Write(m, run_time=run_time)


def _draw_out(m, *, run_time, **_):
    return Create(m, run_time=run_time)


def _grow_up(m, *, run_time, **_):
    # grows from the bottom edge → expands upward
    return GrowFromEdge(m, DOWN, run_time=run_time)


def _grow_down(m, *, run_time, **_):
    return GrowFromEdge(m, UP, run_time=run_time)


def _slide_left(m, *, run_time, distance=1.0, **_):
    # enters moving leftward → starts offset to the right
    return FadeIn(m, shift=RIGHT * distance, run_time=run_time)


def _slide_right(m, *, run_time, distance=1.0, **_):
    return FadeIn(m, shift=LEFT * distance, run_time=run_time)


def _slide_up(m, *, run_time, distance=1.0, **_):
    return FadeIn(m, shift=DOWN * distance, run_time=run_time)


def _slide_down(m, *, run_time, distance=1.0, **_):
    return FadeIn(m, shift=UP * distance, run_time=run_time)


def _level_by_level(m, *, run_time, lag=0.15, **_):
    # Stagger over direct submobjects. If the mobject has none, fall back to FadeIn.
    parts = list(m.submobjects)
    if not parts:
        return FadeIn(m, run_time=run_time)
    return LaggedStart(
        *(FadeIn(p) for p in parts),
        lag_ratio=lag,
        run_time=run_time,
    )


def _count_up(m, *, run_time, target_value, start_value=0, **_):
    """Numeric count-up.

    Components hosting count-up must implement `set_value(value: float)` on
    themselves OR expose `value_mobject` whose `set_value` accepts the value.
    The animation calls `set_value` once per frame with the interpolated value;
    the implementation chooses how to redraw (text replacement, decimal update,
    bar height, etc.).
    """
    target = getattr(m, "value_mobject", m)
    return CountUpAnimation(
        target,
        start_value=start_value,
        target_value=target_value,
        run_time=run_time,
    )


# --- registry ----------------------------------------------------------------

ENTRANCES: dict[str, EffectSpec] = {
    "fade-in":        EffectSpec("fade-in",        _fade_in),
    "write-in":       EffectSpec("write-in",       _write_in),
    "draw-out":       EffectSpec("draw-out",       _draw_out),
    "grow-up":        EffectSpec("grow-up",        _grow_up),
    "grow-down":      EffectSpec("grow-down",      _grow_down),
    "slide-left":     EffectSpec("slide-left",     _slide_left, optional={"distance": 1.0}),
    "slide-right":    EffectSpec("slide-right",    _slide_right, optional={"distance": 1.0}),
    "slide-up":       EffectSpec("slide-up",       _slide_up, optional={"distance": 1.0}),
    "slide-down":     EffectSpec("slide-down",     _slide_down, optional={"distance": 1.0}),
    "level-by-level": EffectSpec("level-by-level", _level_by_level, optional={"lag": 0.15}),
    "count-up":       EffectSpec("count-up",       _count_up,
                                 required=("target_value",),
                                 optional={"start_value": 0}),
}


def get_entrance(name: str, mobject, timing: str, **extra) -> Animation:
    spec = ENTRANCES.get(name)
    if spec is None:
        raise KeyError(
            f"unknown entrance effect {name!r}; available: {sorted(ENTRANCES)}"
        )
    if timing not in TIMING:
        raise KeyError(f"unknown timing {timing!r}; available: {sorted(TIMING)}")
    missing = [k for k in spec.required if k not in extra]
    if missing:
        raise KeyError(
            f"entrance effect {name!r} missing required params: {missing}"
        )
    params = {**spec.optional, **extra}
    return spec.factory(mobject, run_time=TIMING[timing], **params)


def entrance_names() -> list[str]:
    """Sorted list of registered entrance effect names. For schema generation."""
    return sorted(ENTRANCES)

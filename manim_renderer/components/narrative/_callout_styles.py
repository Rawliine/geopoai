"""Visual style variants for CalloutBox.

Four styles ship; `neon` is the default. Each style is a `CalloutStyleSpec`
that defines (a) how to build the bubble around a pre-built text mobject,
(b) the signature entrance animation, (c) the signature exit animation.

Style spec contract (mirrors `EffectSpec` shape):

  build_bubble(text_mob, accent_hex, format) -> VGroup
      Returns a single VGroup containing all decorations (rect, glow halo,
      bracket bar, etc.). The text is NOT placed inside the return value —
      CalloutBox composes bubble + text after this call.

  entrance(bubble_mob, text_mob, timing) -> Animation
      Returns the entrance animation for the bubble + text together. The
      animation should not include the leader line — that's added by
      CalloutBox post-positioning.

  exit(bubble_mob, text_mob, timing) -> Animation
      Symmetric to entrance.

`neon` characteristics:
  - No fill; accent-colored stroke + outer glow.
  - Border traces in via `Create`, then text fades in (`Succession`).
  - On exit, text fades, then border erases via `Uncreate`.

`card` (legacy default before Phase 1.5):
  - Surface fill + border. Whole thing fades together.

`glass`:
  - Translucent dark fill + brighter accent border. Fades together.

`bracket`:
  - No rectangle; just a thick left-edge accent bar. Bar grows from bottom,
  text fades in alongside.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from manim import (
    Animation,
    Create,
    FadeIn,
    FadeOut,
    GrowFromEdge,
    Line,
    RoundedRectangle,
    Succession,
    Uncreate,
    UP,
    VGroup,
)

from manim_renderer.theme.palette import UI
from manim_renderer.theme.timing import TIMING

# Visual constants shared across styles.
_BUBBLE_PADDING_X = 0.35
_BUBBLE_PADDING_Y = 0.20
_CORNER_RADIUS = 0.12
_NEON_BORDER_STROKE = 2.5
_NEON_GLOW_STROKE = 6.0
_NEON_GLOW_OPACITY = 0.25
_CARD_BORDER_STROKE = 1.5
_GLASS_FILL_OPACITY = 0.40
_GLASS_BORDER_STROKE = 2.0
_BRACKET_WIDTH = 0.10
_BRACKET_GAP = 0.20


@dataclass(frozen=True)
class CalloutStyleSpec:
    """Style descriptor for one callout variant. See module docstring."""

    name: str
    build_bubble: Callable
    entrance: Callable[..., Animation]
    exit: Callable[..., Animation]


# --- bubble builders ---------------------------------------------------------


def _neon_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """Two concentric rounded rects — a tight accent border and a wider
    low-opacity halo for the neon glow effect."""
    w = text_mob.width + 2 * _BUBBLE_PADDING_X
    h = text_mob.height + 2 * _BUBBLE_PADDING_Y
    border = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BORDER_STROKE,
        fill_opacity=0.0,
    )
    glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_GLOW_STROKE,
        stroke_opacity=_NEON_GLOW_OPACITY,
        fill_opacity=0.0,
    )
    # Glow first so border sits on top.
    group = VGroup(glow, border)
    group.border = border  # type: ignore[attr-defined]
    group.glow = glow      # type: ignore[attr-defined]
    return group


def _card_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    bubble = RoundedRectangle(
        width=text_mob.width + 2 * _BUBBLE_PADDING_X,
        height=text_mob.height + 2 * _BUBBLE_PADDING_Y,
        corner_radius=_CORNER_RADIUS,
        color=UI["border"],
        fill_color=UI["surface"], fill_opacity=0.95,
        stroke_width=_CARD_BORDER_STROKE,
    )
    return VGroup(bubble)


def _glass_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    bubble = RoundedRectangle(
        width=text_mob.width + 2 * _BUBBLE_PADDING_X,
        height=text_mob.height + 2 * _BUBBLE_PADDING_Y,
        corner_radius=_CORNER_RADIUS,
        color=accent_hex,
        fill_color=UI["background"], fill_opacity=_GLASS_FILL_OPACITY,
        stroke_width=_GLASS_BORDER_STROKE,
    )
    return VGroup(bubble)


def _bracket_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """Just a thick left-edge accent bar — no rectangle. The bar is sized to
    the text's height + small padding."""
    h = text_mob.height + 2 * _BUBBLE_PADDING_Y
    bar = Line(
        start=[0.0, -h / 2, 0.0],
        end=[0.0, h / 2, 0.0],
        color=accent_hex,
        stroke_width=_BRACKET_WIDTH * 100,  # Manim stroke width is in points
    )
    # Position the bar to the left of where the text will sit.
    bar.shift([-text_mob.width / 2 - _BRACKET_GAP, 0.0, 0.0])
    return VGroup(bar)


# --- entrance / exit animations ----------------------------------------------


def _neon_entrance(bubble: VGroup, text, timing: str, **_) -> Animation:
    rt = TIMING[timing]
    # Border traces in, then text fades. Glow appears with border.
    border_anim = Create(bubble, run_time=rt)
    text_anim = FadeIn(text, run_time=TIMING["fast"])
    return Succession(border_anim, text_anim)


def _neon_exit(bubble: VGroup, text, timing: str, **_) -> Animation:
    rt = TIMING[timing]
    text_anim = FadeOut(text, run_time=TIMING["fast"])
    border_anim = Uncreate(bubble, run_time=rt)
    return Succession(text_anim, border_anim)


def _fade_together_entrance(bubble: VGroup, text, timing: str, **_) -> Animation:
    """card / glass: bubble + text fade in together as one group."""
    rt = TIMING[timing]
    return FadeIn(VGroup(bubble, text), run_time=rt)


def _fade_together_exit(bubble: VGroup, text, timing: str, **_) -> Animation:
    rt = TIMING[timing]
    return FadeOut(VGroup(bubble, text), run_time=rt)


def _bracket_entrance(bubble: VGroup, text, timing: str, **_) -> Animation:
    """Bar grows from bottom, text fades in alongside."""
    rt = TIMING[timing]
    bar_anim = GrowFromEdge(bubble, edge=UP, run_time=rt)
    text_anim = FadeIn(text, run_time=rt)
    # Parallel — both animate simultaneously, no Succession needed.
    from manim import AnimationGroup
    return AnimationGroup(bar_anim, text_anim)


def _bracket_exit(bubble: VGroup, text, timing: str, **_) -> Animation:
    rt = TIMING[timing]
    return FadeOut(VGroup(bubble, text), run_time=rt)


# --- registry ----------------------------------------------------------------


CALLOUT_STYLES: dict[str, CalloutStyleSpec] = {
    "neon": CalloutStyleSpec(
        name="neon",
        build_bubble=_neon_bubble,
        entrance=_neon_entrance,
        exit=_neon_exit,
    ),
    "card": CalloutStyleSpec(
        name="card",
        build_bubble=_card_bubble,
        entrance=_fade_together_entrance,
        exit=_fade_together_exit,
    ),
    "glass": CalloutStyleSpec(
        name="glass",
        build_bubble=_glass_bubble,
        entrance=_fade_together_entrance,
        exit=_fade_together_exit,
    ),
    "bracket": CalloutStyleSpec(
        name="bracket",
        build_bubble=_bracket_bubble,
        entrance=_bracket_entrance,
        exit=_bracket_exit,
    ),
}


def get_style(name: str) -> CalloutStyleSpec:
    """Look up a style spec by name. Raises ValueError on unknown name."""
    if name not in CALLOUT_STYLES:
        raise ValueError(
            f"unknown callout style {name!r}; "
            f"available: {sorted(CALLOUT_STYLES)}"
        )
    return CALLOUT_STYLES[name]

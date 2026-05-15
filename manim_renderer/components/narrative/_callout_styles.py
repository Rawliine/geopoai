"""Visual style variants for CalloutBox.

Three styles ship; `neon` is the default. Each style is a `CalloutStyleSpec`
that defines (a) how to build the bubble around a pre-built text mobject,
(b) the signature entrance animation, (c) the signature exit animation.

(Phase 2.0 — PR E: dropped `bracket` style. Replacement variants —
`neon-bold`, `pull-quote`, `inline-tag` — land in PR P alongside the
roles+restaging system.)

Style spec contract (mirrors `EffectSpec` shape):

  build_bubble(text_mob, accent_hex, format) -> VGroup
      Returns a single VGroup containing all decorations (rect, glow halo,
      etc.). The text is NOT placed inside the return value — CalloutBox
      composes bubble + text after this call.

  entrance(bubble_mob, text_mob, timing) -> Animation
      Returns the entrance animation for the bubble + text together. The
      animation should not include the leader line — that's added by
      CalloutBox post-positioning.

  exit(bubble_mob, text_mob, timing) -> Animation
      Symmetric to entrance.

`neon` (default) characteristics:
  - No fill; three concentric strokes (border + mid glow + outer glow) in
    the accent color produce a perceptible halo at preview resolution.
  - Border traces in via `Create`, then text fades in (`Succession`).
  - On exit, text fades, then border erases via `Uncreate`.

`card` (legacy default before Phase 1.5):
  - Surface fill + border. Whole thing fades together.

`glass`:
  - Translucent dark fill + brighter accent border. Fades together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from manim import (
    Animation,
    Create,
    FadeIn,
    FadeOut,
    LEFT,
    RIGHT,
    RoundedRectangle,
    Succession,
    Uncreate,
    VGroup,
)

from manim_renderer.theme.palette import UI, lighten
from manim_renderer.theme.timing import TIMING

# Visual constants shared across styles.
_BUBBLE_PADDING_X = 0.35
_BUBBLE_PADDING_Y = 0.20
_CORNER_RADIUS = 0.12

# Neon stack — Phase 2.0 / PR E2 rewrite:
# 4 concentric strokes mirroring the CSS neon idiom
# (text-shadow: 0 0 5px white, 0 0 10px accent, 0 0 20px accent, 0 0 40px accent):
#
#   1. inner core  — narrow, ~white (lightened accent), full opacity — "hot filament"
#   2. border      — visible line in accent color, near-full opacity
#   3. mid-glow    — wider, accent at mid opacity — close bloom
#   4. outer-glow  — widest, accent at low opacity — wide bloom
#
# Plus a faint interior fill in lightened accent → the "whitish inside" effect
# without dominating the bubble area.
_NEON_INNER_CORE_LIGHTEN = 0.65        # mix accent with white at this fraction
_NEON_INNER_CORE_STROKE = 1.5
_NEON_BORDER_STROKE = 2.5
_NEON_BORDER_OPACITY = 0.95
_NEON_MID_GLOW_STROKE = 8.0
_NEON_MID_GLOW_OPACITY = 0.35
_NEON_OUTER_GLOW_STROKE = 16.0
_NEON_OUTER_GLOW_OPACITY = 0.12
_NEON_INTERIOR_FILL_LIGHTEN = 0.75
_NEON_INTERIOR_FILL_OPACITY = 0.05

_CARD_BORDER_STROKE = 1.5
_GLASS_FILL_OPACITY = 0.40
_GLASS_BORDER_STROKE = 2.0

# PR P — neon-bold dials each of neon's four layers higher and adds an
# extra outer-outer glow for a 5-layer stack. Use sparingly: this style
# dominates the frame.
_NEON_BOLD_INNER_CORE_LIGHTEN = 0.70
_NEON_BOLD_INNER_CORE_STROKE = 2.0
_NEON_BOLD_BORDER_STROKE = 3.5
_NEON_BOLD_BORDER_OPACITY = 1.0
_NEON_BOLD_MID_GLOW_STROKE = 11.0
_NEON_BOLD_MID_GLOW_OPACITY = 0.50
_NEON_BOLD_OUTER_GLOW_STROKE = 22.0
_NEON_BOLD_OUTER_GLOW_OPACITY = 0.22
_NEON_BOLD_OUTER_OUTER_GLOW_STROKE = 36.0
_NEON_BOLD_OUTER_OUTER_GLOW_OPACITY = 0.08
_NEON_BOLD_INTERIOR_FILL_OPACITY = 0.10

# PR P — pull-quote: large stylized quote marks, no bubble, no leader.
# Quote glyphs scale relative to the text height (display-sized).
_PULL_QUOTE_MARK_SCALE = 2.2
_PULL_QUOTE_MARK_OPACITY = 0.85

# PR P — inline-tag: small chip, accent fill, contrast-picked text color.
_INLINE_TAG_PADDING_X = 0.20
_INLINE_TAG_PADDING_Y = 0.10
_INLINE_TAG_CORNER_RADIUS = 0.08


@dataclass(frozen=True)
class CalloutStyleSpec:
    """Style descriptor for one callout variant. See module docstring."""

    name: str
    build_bubble: Callable
    entrance: Callable[..., Animation]
    exit: Callable[..., Animation]


# --- bubble builders ---------------------------------------------------------


def _neon_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """Four-layer neon glow + subtle interior fill — professional design.

    The visual idiom mirrors CSS neon: a hot near-white core surrounded by
    progressively wider, lower-opacity accent-color blooms. The bubble
    interior carries a faint tint of the lightened accent for the
    'whitish inside' effect — present without dominating the area.

    Layer order (back to front, so the inner core sits on top visually):
      1. outer_glow  — widest stroke, very low opacity (wide bloom)
      2. mid_glow    — medium stroke, mid opacity (close bloom)
      3. border      — visible accent line, near-full opacity
      4. inner_core  — narrow stroke in lightened accent, full opacity
                       (the 'hot filament' line)

    The first stroke (outermost) also carries the interior fill so a
    separate fill rect isn't needed — keeps the submobject count to 4.
    """
    w = text_mob.width + 2 * _BUBBLE_PADDING_X
    h = text_mob.height + 2 * _BUBBLE_PADDING_Y

    interior_tint = lighten(accent_hex, _NEON_INTERIOR_FILL_LIGHTEN)
    inner_core_color = lighten(accent_hex, _NEON_INNER_CORE_LIGHTEN)

    outer_glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_OUTER_GLOW_STROKE,
        stroke_opacity=_NEON_OUTER_GLOW_OPACITY,
        fill_color=interior_tint,
        fill_opacity=_NEON_INTERIOR_FILL_OPACITY,
    )
    mid_glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_MID_GLOW_STROKE,
        stroke_opacity=_NEON_MID_GLOW_OPACITY,
        fill_opacity=0.0,
    )
    border = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BORDER_STROKE,
        stroke_opacity=_NEON_BORDER_OPACITY,
        fill_opacity=0.0,
    )
    inner_core = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=inner_core_color, stroke_width=_NEON_INNER_CORE_STROKE,
        stroke_opacity=1.0,
        fill_opacity=0.0,
    )
    group = VGroup(outer_glow, mid_glow, border, inner_core)
    group.inner_core = inner_core   # type: ignore[attr-defined]
    group.border = border           # type: ignore[attr-defined]
    group.mid_glow = mid_glow       # type: ignore[attr-defined]
    group.outer_glow = outer_glow   # type: ignore[attr-defined]
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


# --- PR P bubble builders --------------------------------------------------


def _neon_bold_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """neon-bold: 5-layer stack (extra outer-outer glow), thicker strokes,
    and a slightly stronger interior tint. Use sparingly."""
    w = text_mob.width + 2 * _BUBBLE_PADDING_X
    h = text_mob.height + 2 * _BUBBLE_PADDING_Y

    interior_tint = lighten(accent_hex, _NEON_INTERIOR_FILL_LIGHTEN)
    inner_core_color = lighten(accent_hex, _NEON_BOLD_INNER_CORE_LIGHTEN)

    outer_outer_glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BOLD_OUTER_OUTER_GLOW_STROKE,
        stroke_opacity=_NEON_BOLD_OUTER_OUTER_GLOW_OPACITY,
        fill_color=interior_tint,
        fill_opacity=_NEON_BOLD_INTERIOR_FILL_OPACITY,
    )
    outer_glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BOLD_OUTER_GLOW_STROKE,
        stroke_opacity=_NEON_BOLD_OUTER_GLOW_OPACITY,
        fill_opacity=0.0,
    )
    mid_glow = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BOLD_MID_GLOW_STROKE,
        stroke_opacity=_NEON_BOLD_MID_GLOW_OPACITY,
        fill_opacity=0.0,
    )
    border = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=accent_hex, stroke_width=_NEON_BOLD_BORDER_STROKE,
        stroke_opacity=_NEON_BOLD_BORDER_OPACITY,
        fill_opacity=0.0,
    )
    inner_core = RoundedRectangle(
        width=w, height=h, corner_radius=_CORNER_RADIUS,
        color=inner_core_color, stroke_width=_NEON_BOLD_INNER_CORE_STROKE,
        stroke_opacity=1.0,
        fill_opacity=0.0,
    )
    group = VGroup(outer_outer_glow, outer_glow, mid_glow, border, inner_core)
    group.inner_core = inner_core           # type: ignore[attr-defined]
    group.border = border                   # type: ignore[attr-defined]
    group.mid_glow = mid_glow               # type: ignore[attr-defined]
    group.outer_glow = outer_glow           # type: ignore[attr-defined]
    group.outer_outer_glow = outer_outer_glow  # type: ignore[attr-defined]
    return group


def _pull_quote_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """pull-quote: large display-sized quote marks bracketing the text.

    No bubble fill, no leader line. The accent color is applied to the
    quote glyphs; the text itself uses the CalloutBox's resolved text
    color (auto-contrast from `pick_text_color`).
    """
    from manim import Text as _Text
    open_q = _Text("“", font_size=text_mob.font_size * _PULL_QUOTE_MARK_SCALE)
    close_q = _Text("”", font_size=text_mob.font_size * _PULL_QUOTE_MARK_SCALE)
    open_q.set_color(accent_hex).set_opacity(_PULL_QUOTE_MARK_OPACITY)
    close_q.set_color(accent_hex).set_opacity(_PULL_QUOTE_MARK_OPACITY)
    # Bracket the text: open quote upper-left, close quote lower-right.
    open_q.next_to(text_mob, LEFT, buff=0.18)
    open_q.shift([0.0, text_mob.height * 0.18, 0.0])
    close_q.next_to(text_mob, RIGHT, buff=0.18)
    close_q.shift([0.0, -text_mob.height * 0.18, 0.0])
    return VGroup(open_q, close_q)


def _inline_tag_bubble(text_mob, accent_hex: str, format: str) -> VGroup:
    """inline-tag: small accent-filled chip; no border, no leader."""
    bubble = RoundedRectangle(
        width=text_mob.width + 2 * _INLINE_TAG_PADDING_X,
        height=text_mob.height + 2 * _INLINE_TAG_PADDING_Y,
        corner_radius=_INLINE_TAG_CORNER_RADIUS,
        color=accent_hex,
        fill_color=accent_hex, fill_opacity=1.0,
        stroke_width=0.0,
    )
    return VGroup(bubble)


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
    # PR P — three new variants.
    "neon-bold": CalloutStyleSpec(
        name="neon-bold",
        build_bubble=_neon_bold_bubble,
        entrance=_neon_entrance,
        exit=_neon_exit,
    ),
    "pull-quote": CalloutStyleSpec(
        name="pull-quote",
        build_bubble=_pull_quote_bubble,
        entrance=_fade_together_entrance,
        exit=_fade_together_exit,
    ),
    "inline-tag": CalloutStyleSpec(
        name="inline-tag",
        build_bubble=_inline_tag_bubble,
        entrance=_fade_together_entrance,
        exit=_fade_together_exit,
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

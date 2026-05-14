"""CalloutBox unit tests — bubble construction, leader plumbing, edge selection."""

from __future__ import annotations

import logging

import numpy as np
import pytest
from manim import Square

from manim_renderer.components.narrative.callout_box import (
    CalloutBox,
    _LEADER_EDGES_HORIZONTAL,
    _VERTICAL_FLIP_TOKEN,
)

logging.getLogger("manim").setLevel(logging.ERROR)


# --- construction ------------------------------------------------------------

def test_minimal_construction_with_anchor():
    cb = CalloutBox(
        {"id": "c", "text": "hi", "anchor": "below:foo"},
        format="horizontal",
    )
    assert cb.id == "c"
    assert cb.height > 0 and cb.width > 0
    assert hasattr(cb, "_bubble_mob")
    assert hasattr(cb, "_text_mob")
    assert cb._leader_mob is None  # not added until position_finalized


def test_requires_text():
    with pytest.raises(ValueError, match="text"):
        CalloutBox({"id": "c", "anchor": "below:foo"}, format="horizontal")


def test_requires_anchor():
    with pytest.raises(ValueError, match="anchor"):
        CalloutBox({"id": "c", "text": "hi"}, format="horizontal")


def test_unknown_color_rejected():
    with pytest.raises(ValueError, match="palette key"):
        CalloutBox(
            {"id": "c", "text": "x", "anchor": "below:foo", "color": "puce"},
            format="horizontal",
        )


# --- text wrapping -----------------------------------------------------------

def test_short_text_no_wrap():
    cb = CalloutBox(
        {"id": "c", "text": "tiny", "anchor": "below:foo", "width": 5.0},
        format="horizontal",
    )
    assert "\n" not in cb._text_mob.text


def test_long_text_wraps_to_multiple_lines():
    """Wrapped long text should be visibly taller than short text. Manim's
    `Text.text` strips whitespace, so we measure mobject height instead."""
    long_text = "This callout has more text than fits in a small width " * 3
    cb_long = CalloutBox(
        {"id": "long", "text": long_text, "anchor": "below:foo", "width": 2.0},
        format="horizontal",
    )
    cb_short = CalloutBox(
        {"id": "short", "text": "tiny", "anchor": "below:foo", "width": 5.0},
        format="horizontal",
    )
    # A wrapped multi-line callout is at least 2x as tall as a single line.
    assert cb_long._text_mob.height > cb_short._text_mob.height * 2


# --- position_finalized: leader endpoints ------------------------------------

def _make_target(at):
    s = Square()
    s.move_to(np.asarray(at + [0]) if len(at) == 2 else np.asarray(at))
    return s


@pytest.mark.parametrize("token,bubble_pos,expected_dir", [
    # bubble below target → leader from bubble.top to target.bottom
    ("below",    [0.0, -3.0], "above"),
    # bubble above target → leader from bubble.bottom to target.top
    ("above",    [0.0,  3.0], "below"),
    # bubble right of target → leader from bubble.left to target.right
    ("right-of", [ 3.0, 0.0], "left"),
    # bubble left of target → leader from bubble.right to target.left
    ("left-of",  [-3.0, 0.0], "right"),
])
def test_leader_endpoints_horizontal(token, bubble_pos, expected_dir):
    target = _make_target([0.0, 0.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": f"{token}:t", "width": 2.0},
        format="horizontal",
    )
    cb.move_to(np.array([*bubble_pos, 0.0]))
    cb.position_finalized(anchor=f"{token}:t", target=target, format="horizontal")

    assert cb._leader_mob is not None
    assert cb._leader_endpoints is not None
    bubble_pt, target_pt = cb._leader_endpoints
    # Target endpoint should be the appropriate edge of the unit square
    if expected_dir == "above":
        np.testing.assert_array_almost_equal(target_pt, target.get_bottom())
    elif expected_dir == "below":
        np.testing.assert_array_almost_equal(target_pt, target.get_top())
    elif expected_dir == "left":
        np.testing.assert_array_almost_equal(target_pt, target.get_right())
    elif expected_dir == "right":
        np.testing.assert_array_almost_equal(target_pt, target.get_left())


def test_inside_anchor_no_leader():
    target = _make_target([0.0, 0.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "inside:t"},
        format="horizontal",
    )
    cb.position_finalized(anchor="inside:t", target=target, format="horizontal")
    assert cb._leader_mob is None
    assert cb._leader_endpoints is None


def test_no_target_no_leader():
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:foo"},
        format="horizontal",
    )
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    assert cb._leader_mob is None


def test_arrow_param_changes_leader_class():
    """arrow=True → Arrow; arrow=False → Line."""
    from manim import Arrow, Line
    target = _make_target([0.0, 0.0])

    cb_arrow = CalloutBox(
        {"id": "a", "text": "x", "anchor": "below:t", "arrow": True},
        format="horizontal",
    )
    cb_arrow.move_to(np.array([0.0, -3.0, 0.0]))
    cb_arrow.position_finalized(anchor="below:t", target=target, format="horizontal")
    assert isinstance(cb_arrow._leader_mob, Arrow)

    cb_line = CalloutBox(
        {"id": "b", "text": "x", "anchor": "below:t", "arrow": False},
        format="horizontal",
    )
    cb_line.move_to(np.array([0.0, -3.0, 0.0]))
    cb_line.position_finalized(anchor="below:t", target=target, format="horizontal")
    assert isinstance(cb_line._leader_mob, Line)


# --- vertical-format token flip ----------------------------------------------

def test_vertical_format_flips_lateral_tokens_for_leader():
    """In vertical format, anchor 'right-of:t' resolves to 'below:t' for the
    bubble position; the leader edges must use the same flipped token."""
    target = _make_target([0.0, 0.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "right-of:t"},
        format="vertical",
    )
    # In vertical, right-of flips to below — bubble would be moved below target.
    cb.move_to(np.array([0.0, -3.0, 0.0]))
    cb.position_finalized(anchor="right-of:t", target=target, format="vertical")
    bubble_pt, target_pt = cb._leader_endpoints
    # Leader should land on target's BOTTOM (since flipped to "below")
    np.testing.assert_array_almost_equal(target_pt, target.get_bottom())


# --- head/tail anchors -------------------------------------------------------

def test_head_anchor_returns_target_endpoint():
    target = _make_target([2.0, 1.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "right-of:t"},
        format="horizontal",
    )
    cb.move_to(np.array([5.0, 1.0, 0.0]))
    cb.position_finalized(anchor="right-of:t", target=target, format="horizontal")
    head = cb.get_anchor("head")
    np.testing.assert_array_almost_equal(head, target.get_right())


def test_tail_anchor_returns_bubble_endpoint():
    target = _make_target([2.0, 1.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "right-of:t"},
        format="horizontal",
    )
    cb.move_to(np.array([5.0, 1.0, 0.0]))
    cb.position_finalized(anchor="right-of:t", target=target, format="horizontal")
    tail = cb.get_anchor("tail")
    np.testing.assert_array_almost_equal(tail, cb._bubble_mob.get_left())


def test_head_anchor_raises_when_no_leader():
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:foo"},
        format="horizontal",
    )
    with pytest.raises(KeyError, match="head"):
        cb.get_anchor("head")


def test_tail_anchor_raises_when_no_leader():
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:foo"},
        format="horizontal",
    )
    with pytest.raises(KeyError, match="tail"):
        cb.get_anchor("tail")


# --- entrance dispatching ----------------------------------------------------

def test_fade_in_entrance_with_leader_uses_succession():
    from manim import Succession
    target = _make_target([0.0, 0.0])
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:t"},
        format="horizontal",
    )
    cb.move_to(np.array([0.0, -3.0, 0.0]))
    cb.position_finalized(anchor="below:t", target=target, format="horizontal")
    anim = cb.entrance("fade-in", "normal")
    assert isinstance(anim, Succession)


def test_fade_in_entrance_without_leader_is_fade_in():
    from manim import FadeIn
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "inside:foo"},
        format="horizontal",
    )
    target = _make_target([0.0, 0.0])
    cb.position_finalized(anchor="inside:foo", target=target, format="horizontal")
    anim = cb.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)


# --- both formats ------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build(fmt):
    cb = CalloutBox(
        {"id": "c", "text": "test text", "anchor": "below:foo", "width": 3.0},
        format=fmt,
    )
    assert cb.width > 0 and cb.height > 0


# --- edge table sanity -------------------------------------------------------

def test_leader_edges_table_complete_for_all_tokens():
    """Every anchor token resolve_anchor supports must have a leader-edges entry."""
    from manim_renderer.resolvers.anchor import ANCHOR_TOKENS
    for tok in ANCHOR_TOKENS:
        assert tok in _LEADER_EDGES_HORIZONTAL, (
            f"Anchor token {tok!r} has no leader-edges mapping in CalloutBox"
        )


# --- Phase 1.5: style system -------------------------------------------------


@pytest.mark.parametrize("style", ["neon", "card", "glass"])
def test_each_style_constructs(style):
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": style},
        format="horizontal",
    )
    assert cb._style_name == style
    assert cb._bubble_mob is not None
    assert cb._text_mob is not None


def test_default_style_is_neon():
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t"},
        format="horizontal",
    )
    assert cb._style_name == "neon"


def test_unknown_style_rejected():
    with pytest.raises(ValueError, match="unknown"):
        CalloutBox(
            {"id": "c", "text": "demo", "anchor": "below:t", "style": "puce"},
            format="horizontal",
        )


def test_neon_entrance_uses_succession_with_text():
    """Neon's signature entrance traces border then fades text — Succession."""
    from manim import Succession
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "neon"},
        format="horizontal",
    )
    # No leader (no target passed to position_finalized).
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    # Pass a non-generic effect name so it routes to the style entrance.
    anim = cb.entrance("draw-out", "normal")
    assert isinstance(anim, Succession)


def test_card_entrance_uses_fade_in_group():
    """Card's signature entrance fades bubble + text as one."""
    from manim import FadeIn
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "card"},
        format="horizontal",
    )
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    # Use an effect outside the generic list to hit the style path.
    anim = cb.entrance("draw-out", "normal")
    assert isinstance(anim, FadeIn)


def test_neon_bubble_has_four_layers():
    """Phase 2.0 / PR E2: professional neon stack is four concentric strokes
    (outer glow + mid glow + border + inner core). Asserts the structural
    shape so future tweaks don't silently collapse the layers."""
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "neon"},
        format="horizontal",
    )
    # bubble_mob is a VGroup of (outer_glow, mid_glow, border, inner_core).
    assert len(cb._bubble_mob.submobjects) == 4
    # Named accessors are present (used by future restage / Transform code).
    for name in ("outer_glow", "mid_glow", "border", "inner_core"):
        assert hasattr(cb._bubble_mob, name), f"neon bubble missing {name!r}"


def test_bracket_style_rejected():
    """Phase 2.0: `bracket` was dropped. Constructing a CalloutBox with
    style='bracket' should fail with the unknown-style error."""
    with pytest.raises(ValueError, match="unknown"):
        CalloutBox(
            {"id": "c", "text": "demo", "anchor": "below:t", "style": "bracket"},
            format="horizontal",
        )


def test_explicit_fade_in_effect_overrides_style_default():
    """When the author explicitly requests fade-in, the style's signature
    animation is bypassed in favor of the generic entrance."""
    from manim import FadeIn
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "neon"},
        format="horizontal",
    )
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    anim = cb.entrance("fade-in", "normal")
    # fade-in routes through generic get_entrance → FadeIn.
    assert isinstance(anim, FadeIn)


def test_neon_exit_uses_succession():
    from manim import Succession
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "neon"},
        format="horizontal",
    )
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    # Non-generic effect so it routes to style.
    anim = cb.exit("dramatic-trace", "normal")
    assert isinstance(anim, Succession)


def test_fade_out_exit_routes_through_super():
    """Generic exit effect names (fade-out, dissolve) bypass style spec."""
    from manim import FadeOut
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": "neon"},
        format="horizontal",
    )
    cb.position_finalized(anchor=None, target=None, format="horizontal")
    anim = cb.exit("fade-out", "fast")
    assert isinstance(anim, FadeOut)


@pytest.mark.parametrize("style", ["neon", "glass"])
def test_transparent_styles_use_auto_contrast_text(style):
    """For non-card styles (transparent background), text color is picked
    by luminance against the scene background (#0e1116 → dark → light text)."""
    from manim_renderer.theme.palette import UI
    cb = CalloutBox(
        {"id": "c", "text": "demo", "anchor": "below:t", "style": style},
        format="horizontal",
    )
    # The text color should match text_primary against the dark background.
    expected = UI["text_primary"]
    actual_hex = cb._text_mob.color.to_hex().upper()
    assert actual_hex.upper() == expected.upper(), (
        f"style={style}: text color {actual_hex} != expected {expected}"
    )


# --- pick_text_color auto-contrast helper -----------------------------------


def test_pick_text_color_dark_bg_returns_light():
    from manim_renderer.theme.palette import UI, pick_text_color
    assert pick_text_color(UI["background"]) == UI["text_primary"]


def test_pick_text_color_light_bg_returns_dark():
    from manim_renderer.theme.palette import UI, pick_text_color
    assert pick_text_color("#ffffff") == UI["background"]

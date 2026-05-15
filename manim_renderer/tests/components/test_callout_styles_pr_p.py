"""PR P — three new CalloutBox styles: neon-bold, pull-quote, inline-tag.

Per-style contracts:
  * `neon-bold` — 5-layer stack (outer-outer-glow + 4 neon layers).
  * `pull-quote` — no rounded rect bubble; two quote-mark glyphs bracket
    the text. No leader line.
  * `inline-tag` — single chip rect with solid accent fill; no leader.

Each test instantiates a real CalloutBox so the style dispatch + bubble
construction path is fully exercised.
"""

from __future__ import annotations

import logging

import pytest
from manim import RoundedRectangle, Text

from manim_renderer.components.narrative._callout_styles import CALLOUT_STYLES
from manim_renderer.components.narrative.callout_box import CalloutBox

logging.getLogger("manim").setLevel(logging.ERROR)


@pytest.mark.parametrize("style", ["neon-bold", "pull-quote", "inline-tag"])
def test_style_is_in_registry(style):
    assert style in CALLOUT_STYLES


def test_neon_bold_has_five_layers():
    cb = CalloutBox(
        {"id": "c", "text": "headline", "anchor": "below:foo",
         "style": "neon-bold"},
        format="horizontal",
    )
    # _bubble_mob is a VGroup of decorations. neon-bold has 5 sub-rects.
    assert len(cb._bubble_mob.submobjects) == 5


def test_neon_default_still_has_four_layers():
    cb = CalloutBox(
        {"id": "c", "text": "headline", "anchor": "below:foo",
         "style": "neon"},
        format="horizontal",
    )
    assert len(cb._bubble_mob.submobjects) == 4


def test_pull_quote_no_rounded_rect():
    cb = CalloutBox(
        {"id": "c", "text": "thematic", "anchor": "below:foo",
         "style": "pull-quote"},
        format="horizontal",
    )
    # pull-quote uses Text glyphs (the quote marks), not a RoundedRectangle.
    for sub in cb._bubble_mob.submobjects:
        assert not isinstance(sub, RoundedRectangle), (
            "pull-quote should have no rounded-rect bubble"
        )
    # Two glyph mobjects (open and close quotes).
    assert len(cb._bubble_mob.submobjects) == 2


def test_inline_tag_single_chip():
    cb = CalloutBox(
        {"id": "c", "text": "Equilibrium", "anchor": "below:foo",
         "style": "inline-tag"},
        format="horizontal",
    )
    # inline-tag = one filled RoundedRectangle.
    assert len(cb._bubble_mob.submobjects) == 1
    assert isinstance(cb._bubble_mob.submobjects[0], RoundedRectangle)


# --- leader suppression for pull-quote and inline-tag ----------------------


class _FakeTarget:
    """Minimal mobject-like for position_finalized: bbox accessors only."""
    def get_top(self): return [0.0, 1.0, 0.0]
    def get_bottom(self): return [0.0, -1.0, 0.0]
    def get_left(self): return [-1.0, 0.0, 0.0]
    def get_right(self): return [1.0, 0.0, 0.0]
    def get_center(self): return [0.0, 0.0, 0.0]


@pytest.mark.parametrize("style", ["pull-quote", "inline-tag"])
def test_no_leader_for_pull_quote_or_inline_tag(style):
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:foo", "style": style},
        format="horizontal",
    )
    cb.position_finalized(
        anchor="below:foo", target=_FakeTarget(), format="horizontal",
    )
    assert cb._leader_mob is None, (
        f"{style} should not draw a leader line"
    )


def test_neon_still_draws_leader_by_default():
    cb = CalloutBox(
        {"id": "c", "text": "x", "anchor": "below:foo", "style": "neon"},
        format="horizontal",
    )
    cb.position_finalized(
        anchor="below:foo", target=_FakeTarget(), format="horizontal",
    )
    assert cb._leader_mob is not None

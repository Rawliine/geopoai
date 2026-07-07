"""The `caption` token was overloaded: burned-in subtitles, manim callouts, and
manim small-text (axes/timeline) all read it, so enlarging subtitles ballooned
charts and callouts. These lock in the split into `subtitle` / `callout` /
`caption` so each can move independently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "config" / "design_tokens.json").read_text())
SCALE = TOKENS["typography"]["scale"]


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_scale_has_distinct_roles(fmt):
    s = SCALE[fmt]
    for role in ("caption", "callout", "subtitle"):
        assert role in s, f"{fmt} scale missing {role!r}"
    # subtitles are the largest (short-form legibility); caption stays smallest.
    assert s["subtitle"] > s["callout"] >= s["caption"]


def test_burned_in_caption_uses_subtitle_size():
    from composition import captions

    assert captions._caption_font_size(TOKENS, "vertical") == SCALE["vertical"]["subtitle"]
    assert captions._caption_font_size(TOKENS, "horizontal") == SCALE["horizontal"]["subtitle"]


def test_manim_callout_uses_callout_size_not_caption():
    from manim_renderer.components.narrative.callout_box import _callout_font_size
    from manim_renderer.theme.typography import FONT_SCALE

    for fmt in ("horizontal", "vertical"):
        assert _callout_font_size(fmt) == FONT_SCALE[fmt]["callout"]
        # decoupled: callout size is independent of the caption role
        assert _callout_font_size(fmt) != FONT_SCALE[fmt]["caption"] or (
            FONT_SCALE[fmt]["callout"] == FONT_SCALE[fmt]["caption"]
        )


def test_manim_caption_role_stays_small():
    """Axes/timeline/flywheel small-text read `caption`; enlarging subtitles must
    not have grown it."""
    from manim_renderer.theme.typography import FONT_SCALE

    assert FONT_SCALE["vertical"]["caption"] <= 30
    assert FONT_SCALE["horizontal"]["caption"] <= 24

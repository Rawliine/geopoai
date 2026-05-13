"""StatBlock unit tests. Construction + anchor lookup + count-up plumbing.

No MP4 rendering — render-test of StatBlock is exercised via the Phase 1 PD
scene integration test in tests/scripts/.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from manim_renderer.components.data_viz.stat_block import StatBlock
from manim_renderer.effects._animations import CountUpAnimation

# Suppress Manim's font-fallback warnings during unit tests.
logging.getLogger("manim").setLevel(logging.ERROR)


# --- minimal construction ----------------------------------------------------

def test_minimal_construction():
    sb = StatBlock(
        {"id": "s", "value": 42, "label": "Defect rate"},
        format="horizontal",
    )
    assert sb.id == "s"
    assert sb.height > 0 and sb.width > 0
    assert hasattr(sb, "_value_mob")
    assert hasattr(sb, "_label_mob")
    # Optional pieces absent
    assert not hasattr(sb, "_unit_mob")
    assert not hasattr(sb, "_trend_mob")
    assert not hasattr(sb, "_spark_mob")


def test_requires_value():
    with pytest.raises(ValueError, match="value"):
        StatBlock({"id": "s", "label": "x"}, format="horizontal")


def test_requires_label():
    with pytest.raises(ValueError, match="label"):
        StatBlock({"id": "s", "value": 1}, format="horizontal")


def test_unknown_value_format_raises():
    with pytest.raises(ValueError, match="value_format"):
        StatBlock(
            {"id": "s", "value": 1, "label": "x", "value_format": "lobster"},
            format="horizontal",
        )


def test_unknown_color_raises():
    with pytest.raises(ValueError, match="palette key"):
        StatBlock(
            {"id": "s", "value": 1, "label": "x", "color": "puce"},
            format="horizontal",
        )


# --- both formats ------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_both_formats_build_without_error(fmt):
    sb = StatBlock(
        {"id": "s", "value": 99.5, "label": "test",
         "unit": "%", "trend": {"delta": 1, "direction": "up"},
         "sparkline": [1, 2, 3, 4, 5]},
        format=fmt,
    )
    assert sb.width > 0 and sb.height > 0


# --- optional pieces ---------------------------------------------------------

def test_unit_added_when_provided():
    sb = StatBlock({"id": "s", "value": 1, "label": "x", "unit": "%"}, "horizontal")
    assert hasattr(sb, "_unit_mob")


def test_trend_requires_delta_and_direction():
    with pytest.raises(ValueError, match="delta"):
        StatBlock({"id": "s", "value": 1, "label": "x", "trend": {"direction": "up"}}, "horizontal")


def test_trend_unknown_direction_rejected():
    with pytest.raises(ValueError, match="direction"):
        StatBlock(
            {"id": "s", "value": 1, "label": "x",
             "trend": {"delta": 1, "direction": "sideways"}},
            "horizontal",
        )


def test_sparkline_requires_min_two_points():
    with pytest.raises(ValueError, match="at least 2 points"):
        StatBlock({"id": "s", "value": 1, "label": "x", "sparkline": [5]}, "horizontal")


# --- anchors -----------------------------------------------------------------

def test_standard_anchors_inherited():
    sb = StatBlock({"id": "s", "value": 1, "label": "x"}, "horizontal")
    for name in ("top", "bottom", "left", "right", "center",
                 "top-left", "top-right", "bottom-left", "bottom-right"):
        coord = sb.get_anchor(name)
        assert coord.shape == (3,)


def test_custom_value_anchor_returns_value_mob_center():
    sb = StatBlock({"id": "s", "value": 42, "label": "test"}, "horizontal")
    np.testing.assert_array_almost_equal(
        sb.get_anchor("value"), sb._value_mob.get_center()
    )


def test_custom_label_anchor_returns_label_mob_center():
    sb = StatBlock({"id": "s", "value": 42, "label": "test"}, "horizontal")
    np.testing.assert_array_almost_equal(
        sb.get_anchor("label"), sb._label_mob.get_center()
    )


def test_unit_anchor_raises_when_no_unit():
    sb = StatBlock({"id": "s", "value": 1, "label": "x"}, "horizontal")
    with pytest.raises(KeyError, match="unit"):
        sb.get_anchor("unit")


def test_trend_anchor_raises_when_no_trend():
    sb = StatBlock({"id": "s", "value": 1, "label": "x"}, "horizontal")
    with pytest.raises(KeyError, match="trend"):
        sb.get_anchor("trend")


def test_sparkline_anchor_raises_when_no_sparkline():
    sb = StatBlock({"id": "s", "value": 1, "label": "x"}, "horizontal")
    with pytest.raises(KeyError, match="sparkline"):
        sb.get_anchor("sparkline")


# --- count-up plumbing -------------------------------------------------------

def test_set_value_updates_value_mob_in_place():
    sb = StatBlock({"id": "s", "value": 100, "label": "x"}, "horizontal")
    original_id = id(sb._value_mob)
    sb.set_value(42)
    assert id(sb._value_mob) != original_id, "value mob should be replaced"
    # The new mob should display the formatted value (default int → "42")
    # We don't check pixel content but we do confirm the mob is a Text instance.
    from manim import Text
    assert isinstance(sb._value_mob, Text)


def test_count_up_entrance_returns_animation_group_when_extras_present():
    """With sparkline/trend/unit, count-up returns AnimationGroup of count + FadeIn."""
    from manim import AnimationGroup
    sb = StatBlock(
        {"id": "s", "value": 100, "label": "x", "unit": "%",
         "sparkline": [1, 2, 3]},
        "horizontal",
    )
    anim = sb.entrance("count-up", "normal")
    assert isinstance(anim, AnimationGroup)


def test_count_up_entrance_returns_count_only_when_no_extras():
    sb = StatBlock({"id": "s", "value": 100, "label": "lbl"}, "horizontal")
    # No unit, no trend, no sparkline → only the value + label exist.
    # The label is also a "non-value child", so AnimationGroup applies.
    # But if we override to an empty case (only value), CountUpAnimation alone.
    # The current implementation always has a label, so AnimationGroup expected.
    from manim import AnimationGroup
    anim = sb.entrance("count-up", "normal")
    assert isinstance(anim, AnimationGroup)


def test_count_up_uses_current_value_as_default_target():
    sb = StatBlock({"id": "s", "value": 75.5, "label": "x"}, "horizontal")
    # No target_value passed; should default to params.value.
    anim = sb.entrance("count-up", "normal")
    # Find the CountUpAnimation in the group
    inner = anim.animations[0] if hasattr(anim, "animations") else anim
    assert isinstance(inner, CountUpAnimation)
    assert inner.target_value == 75.5
    assert inner.start_value == 0.0


def test_other_effects_dispatch_to_base():
    """Non-count-up effects should pass through to BaseComponent's default."""
    from manim import FadeIn
    sb = StatBlock({"id": "s", "value": 1, "label": "x"}, "horizontal")
    anim = sb.entrance("fade-in", "normal")
    assert isinstance(anim, FadeIn)

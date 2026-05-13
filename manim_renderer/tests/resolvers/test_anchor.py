"""Anchor resolver unit tests. No rendering — pure function tests."""

from __future__ import annotations

import numpy as np
import pytest
from manim import Square

from manim_renderer.resolvers.anchor import (
    ANCHOR_TOKENS,
    parse_anchor,
    resolve_anchor,
)

PADDING = 0.5


def _registry():
    s = Square()  # 2x2 square at origin
    s.move_to([3.0, 1.0, 0.0])  # center at (3, 1)
    return {"sq": s}


def test_parse_anchor_valid_tokens():
    for token in ANCHOR_TOKENS:
        t, ident = parse_anchor(f"{token}:foo")
        assert t == token and ident == "foo"


def test_parse_anchor_missing_separator():
    with pytest.raises(ValueError, match="missing ':'"):
        parse_anchor("below")


def test_parse_anchor_unknown_token():
    with pytest.raises(ValueError, match="not in"):
        parse_anchor("nearby:foo")


def test_parse_anchor_empty_id():
    with pytest.raises(ValueError, match="empty id"):
        parse_anchor("below:")


@pytest.mark.parametrize(
    "anchor, expected",
    [
        ("above:sq",    [3.0,  2.0 + PADDING, 0.0]),
        ("below:sq",    [3.0,  0.0 - PADDING, 0.0]),
        ("right-of:sq", [4.0 + PADDING, 1.0, 0.0]),
        ("left-of:sq",  [2.0 - PADDING, 1.0, 0.0]),
        ("inside:sq",   [3.0, 1.0, 0.0]),
    ],
)
def test_resolve_anchor_horizontal(anchor, expected):
    coord = resolve_anchor(anchor, _registry(), "horizontal", padding=PADDING)
    np.testing.assert_allclose(coord, expected, atol=1e-9)


def test_vertical_auto_flip_right_of_becomes_below():
    coord = resolve_anchor("right-of:sq", _registry(), "vertical", padding=PADDING)
    expected = [3.0, 0.0 - PADDING, 0.0]
    np.testing.assert_allclose(coord, expected, atol=1e-9)


def test_vertical_auto_flip_left_of_becomes_above():
    coord = resolve_anchor("left-of:sq", _registry(), "vertical", padding=PADDING)
    expected = [3.0, 2.0 + PADDING, 0.0]
    np.testing.assert_allclose(coord, expected, atol=1e-9)


def test_strict_axis_disables_flip_in_vertical():
    coord = resolve_anchor(
        "right-of:sq", _registry(), "vertical", padding=PADDING, strict_axis=True
    )
    expected = [4.0 + PADDING, 1.0, 0.0]
    np.testing.assert_allclose(coord, expected, atol=1e-9)


def test_above_below_unaffected_by_format():
    h = resolve_anchor("above:sq", _registry(), "horizontal", padding=PADDING)
    v = resolve_anchor("above:sq", _registry(), "vertical", padding=PADDING)
    np.testing.assert_allclose(h, v, atol=1e-9)


def test_unknown_target_id_raises():
    with pytest.raises(ValueError, match="not in id registry"):
        resolve_anchor("below:nope", _registry(), "horizontal")


def test_zero_padding():
    coord = resolve_anchor("above:sq", _registry(), "horizontal", padding=0.0)
    np.testing.assert_allclose(coord, [3.0, 2.0, 0.0], atol=1e-9)


# --- place_at_anchor ---------------------------------------------------------

from manim_renderer.resolvers.anchor import DEFAULT_ANCHOR_BUFF, place_at_anchor


def _make_target_and_component(target_pos=(0.0, 0.0, 0.0), component_size=2.0):
    """Build two non-overlapping squares — one as anchor target, one as
    the component to place. Both 2x2 by default."""
    target = Square()  # 2x2 at origin
    target.move_to(target_pos)
    component = Square(side_length=component_size)
    component.move_to([10.0, 10.0, 0.0])  # offscreen — place_at_anchor must move it
    return target, component


def test_place_below_puts_component_top_at_target_bottom_minus_buff():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "below:t", "horizontal")
    # Component's top should sit DEFAULT_ANCHOR_BUFF below target's bottom.
    expected_top_y = target.get_bottom()[1] - DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_top()[1], expected_top_y, atol=1e-6)


def test_place_above_puts_component_bottom_at_target_top_plus_buff():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "above:t", "horizontal")
    expected_bottom_y = target.get_top()[1] + DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_bottom()[1], expected_bottom_y, atol=1e-6)


def test_place_right_of_puts_component_left_at_target_right_plus_buff():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "right-of:t", "horizontal")
    expected_left_x = target.get_right()[0] + DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_left()[0], expected_left_x, atol=1e-6)


def test_place_left_of_puts_component_right_at_target_left_minus_buff():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "left-of:t", "horizontal")
    expected_right_x = target.get_left()[0] - DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_right()[0], expected_right_x, atol=1e-6)


def test_place_inside_puts_component_at_target_center():
    target, comp = _make_target_and_component(target_pos=(2.0, 1.0, 0.0))
    place_at_anchor(comp, target, "inside:t", "horizontal")
    np.testing.assert_allclose(comp.get_center(), target.get_center(), atol=1e-6)


def test_place_no_overlap_when_target_and_component_same_size():
    """Critical regression test — verify placed component does NOT overlap target."""
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    for token in ("above", "below", "left-of", "right-of"):
        target_b, comp_b = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
        place_at_anchor(comp_b, target_b, f"{token}:t", "horizontal")
        # No overlap: at least one axis has the component fully outside target bounds.
        comp_l, comp_r = comp_b.get_left()[0], comp_b.get_right()[0]
        comp_b_y, comp_t_y = comp_b.get_bottom()[1], comp_b.get_top()[1]
        tgt_l, tgt_r = target_b.get_left()[0], target_b.get_right()[0]
        tgt_b_y, tgt_t_y = target_b.get_bottom()[1], target_b.get_top()[1]
        x_disjoint = comp_r <= tgt_l or comp_l >= tgt_r
        y_disjoint = comp_t_y <= tgt_b_y or comp_b_y >= tgt_t_y
        assert x_disjoint or y_disjoint, (
            f"token {token!r}: component overlaps target — "
            f"comp x[{comp_l:.2f},{comp_r:.2f}] y[{comp_b_y:.2f},{comp_t_y:.2f}], "
            f"target x[{tgt_l:.2f},{tgt_r:.2f}] y[{tgt_b_y:.2f},{tgt_t_y:.2f}]"
        )


def test_place_vertical_format_flips_lateral_tokens():
    """In vertical, right-of should auto-flip to below."""
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "right-of:t", "vertical")
    # Should behave like "below:t" — component top below target bottom.
    expected_top_y = target.get_bottom()[1] - DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_top()[1], expected_top_y, atol=1e-6)


def test_place_strict_axis_disables_flip():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "right-of:t", "vertical", strict_axis=True)
    # Should still be right-of: component left at target right + buff.
    expected_left_x = target.get_right()[0] + DEFAULT_ANCHOR_BUFF
    np.testing.assert_allclose(comp.get_left()[0], expected_left_x, atol=1e-6)


def test_place_custom_buff():
    target, comp = _make_target_and_component(target_pos=(0.0, 0.0, 0.0))
    place_at_anchor(comp, target, "below:t", "horizontal", buff=1.5)
    expected_top_y = target.get_bottom()[1] - 1.5
    np.testing.assert_allclose(comp.get_top()[1], expected_top_y, atol=1e-6)

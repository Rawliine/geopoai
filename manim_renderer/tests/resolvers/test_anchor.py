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

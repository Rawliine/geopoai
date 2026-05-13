"""Size resolver unit tests."""

from __future__ import annotations

import pytest

from manim_renderer.resolvers.size import (
    SIZE_KINDS,
    SIZE_ROLES,
    SIZE_TABLE,
    resolve_size,
)


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
@pytest.mark.parametrize("kind", SIZE_KINDS)
@pytest.mark.parametrize("role", SIZE_ROLES)
def test_table_is_complete(fmt, kind, role):
    """Every (format, kind, role) triple has a (width, height) entry."""
    w, h = resolve_size(role, fmt, kind)
    assert w > 0 and h > 0


@pytest.mark.parametrize("kind", SIZE_KINDS)
def test_size_grows_monotonically_per_kind(kind):
    for fmt in ("horizontal", "vertical"):
        small_w, small_h = SIZE_TABLE[fmt][kind]["small"]
        med_w, med_h = SIZE_TABLE[fmt][kind]["medium"]
        large_w, large_h = SIZE_TABLE[fmt][kind]["large"]
        assert small_w * small_h <= med_w * med_h <= large_w * large_h, (
            f"size area must grow monotonically for ({fmt}, {kind})"
        )


def test_unknown_format_raises():
    with pytest.raises(KeyError, match="unknown format"):
        resolve_size("medium", "diagonal")


def test_unknown_kind_raises():
    with pytest.raises(KeyError, match="unknown kind"):
        resolve_size("medium", "horizontal", kind="nonsense")


def test_unknown_role_raises():
    with pytest.raises(KeyError, match="unknown role"):
        resolve_size("huge", "horizontal")


def test_dims_fit_in_horizontal_frame():
    """Manim horizontal frame is 14.2x8.0. Large sizes should fit."""
    for kind in SIZE_KINDS:
        w, h = resolve_size("large", "horizontal", kind)
        assert w <= 14.2 and h <= 8.0, f"{kind}/large {w}x{h} overflows horizontal frame"


def test_dims_fit_in_vertical_frame():
    """Manim vertical frame is 8.0x14.2."""
    for kind in SIZE_KINDS:
        w, h = resolve_size("large", "vertical", kind)
        assert w <= 8.0 and h <= 14.2, f"{kind}/large {w}x{h} overflows vertical frame"

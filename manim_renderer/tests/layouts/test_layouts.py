"""Layout invariants and format/layout compatibility tests."""

from __future__ import annotations

import copy

import pytest

from manim_renderer.layouts.horizontal import HORIZONTAL_LAYOUTS
from manim_renderer.layouts.vertical import VERTICAL_LAYOUTS
from manim_renderer.schema.validator import LAYOUT_FORMATS, validate

# Manim frame dimensions (must match pipeline/render_manim.py:_FORMAT_FRAME).
_FRAME = {
    "horizontal": (14.2, 8.0),
    "vertical":   (8.0, 14.2),
}


# --- structural invariants ----------------------------------------------------

@pytest.mark.parametrize("fmt,layouts", [
    ("horizontal", HORIZONTAL_LAYOUTS),
    ("vertical", VERTICAL_LAYOUTS),
])
def test_layout_format_matches_family(fmt, layouts):
    for name, layout in layouts.items():
        assert layout.format == fmt, (
            f"layout {name!r} in {fmt} family declares format={layout.format!r}"
        )


@pytest.mark.parametrize("fmt,layouts", [
    ("horizontal", HORIZONTAL_LAYOUTS),
    ("vertical", VERTICAL_LAYOUTS),
])
def test_slots_fit_in_frame(fmt, layouts):
    fw, fh = _FRAME[fmt]
    half_w, half_h = fw / 2, fh / 2
    for layout_name, layout in layouts.items():
        for slot_name, rect in layout.slots.items():
            x_min = rect.cx - rect.width / 2
            x_max = rect.cx + rect.width / 2
            y_min = rect.cy - rect.height / 2
            y_max = rect.cy + rect.height / 2
            assert -half_w <= x_min and x_max <= half_w, (
                f"slot {layout_name}.{slot_name} x ∈ [{x_min}, {x_max}] "
                f"exceeds frame ±{half_w}"
            )
            assert -half_h <= y_min and y_max <= half_h, (
                f"slot {layout_name}.{slot_name} y ∈ [{y_min}, {y_max}] "
                f"exceeds frame ±{half_h}"
            )


@pytest.mark.parametrize("fmt,layouts", [
    ("horizontal", HORIZONTAL_LAYOUTS),
    ("vertical", VERTICAL_LAYOUTS),
])
def test_slot_names_are_nonempty(fmt, layouts):
    for layout_name, layout in layouts.items():
        assert layout.slots, f"layout {layout_name!r} ({fmt}) has no slots"
        for slot_name in layout.slots:
            assert slot_name and isinstance(slot_name, str)


def test_layout_format_compat_map_matches_implementations():
    """LAYOUT_FORMATS is the source of truth for the validator; it must list
    exactly the layouts implemented in horizontal.py + vertical.py."""
    impl_h = set(HORIZONTAL_LAYOUTS)
    impl_v = set(VERTICAL_LAYOUTS)
    for name, formats in LAYOUT_FORMATS.items():
        if "horizontal" in formats:
            assert name in impl_h, (
                f"LAYOUT_FORMATS lists {name!r} as horizontal but it isn't in "
                f"HORIZONTAL_LAYOUTS"
            )
        if "vertical" in formats:
            assert name in impl_v, (
                f"LAYOUT_FORMATS lists {name!r} as vertical but it isn't in "
                f"VERTICAL_LAYOUTS"
            )
    # Reverse: every implemented layout must be in LAYOUT_FORMATS
    for name in impl_h:
        assert name in LAYOUT_FORMATS, f"horizontal layout {name!r} missing from LAYOUT_FORMATS"
        assert "horizontal" in LAYOUT_FORMATS[name]
    for name in impl_v:
        assert name in LAYOUT_FORMATS, f"vertical layout {name!r} missing from LAYOUT_FORMATS"
        assert "vertical" in LAYOUT_FORMATS[name]


# --- format/layout compat enforcement via validator --------------------------

_BASE = {
    "renderer": "manim",
    "format": "horizontal",
    "quality": "preview",
    "scene": {"layout": "hero", "duration": 5},
    "slots": {},
    "overlays": [],
    "timeline": [],
}


def _scene(format: str, layout: str, slots: dict | None = None):
    s = copy.deepcopy(_BASE)
    s["format"] = format
    s["scene"]["layout"] = layout
    if slots:
        s["slots"] = slots
    return s


def test_split_in_vertical_rejected():
    scene = _scene("vertical", "split")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "split" in e for e in errs), errs


def test_stacked_in_horizontal_rejected():
    scene = _scene("horizontal", "stacked")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "stacked" in e for e in errs), errs


def test_data_left_in_vertical_rejected():
    scene = _scene("vertical", "data-left")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "data-left" in e for e in errs), errs


def test_data_top_in_horizontal_rejected():
    scene = _scene("horizontal", "data-top")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "data-top" in e for e in errs), errs


def test_trio_in_vertical_rejected():
    scene = _scene("vertical", "trio")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "trio" in e for e in errs), errs


def test_trio_stack_in_horizontal_rejected():
    scene = _scene("horizontal", "trio-stack")
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-format" in e and "trio-stack" in e for e in errs), errs


def test_title_body_works_in_both_formats():
    for fmt in ("horizontal", "vertical"):
        ok, errs = validate(_scene(fmt, "title-body"))
        assert ok, f"{fmt}: {errs}"


def test_unknown_layout_rejected_by_schema_enum():
    scene = _scene("horizontal", "nonsense-layout")
    ok, errs = validate(scene)
    assert not ok
    # Schema-level enum kicks in first (structural tier), but layout-unknown
    # may also fire. Either is a fail signal — just assert at least one error.
    assert errs


def test_split_with_correct_slots_passes():
    scene = _scene(
        "horizontal", "split",
        slots={
            "left":  {"at": 0.0, "action": "showTextCard",
                      "params": {"id": "a", "text": "A"}},
            "right": {"at": 0.0, "action": "showTextCard",
                      "params": {"id": "b", "text": "B"}},
        },
    )
    ok, errs = validate(scene)
    assert ok, errs


def test_split_with_wrong_slot_rejected():
    scene = _scene(
        "horizontal", "split",
        slots={
            "main": {"at": 0.0, "action": "showTextCard",
                     "params": {"id": "a", "text": "A"}},
        },
    )
    ok, errs = validate(scene)
    assert not ok
    assert any("layout-slot" in e and "main" in e for e in errs), errs

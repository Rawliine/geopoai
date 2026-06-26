"""Guard linter rejection tests and contract smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from manim_renderer.escape_hatch.contract import parse_escape_hatch
from manim_renderer.escape_hatch.guard import GuardViolation, lint_scene_file

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_escape_hatch_valid():
    spec = parse_escape_hatch({
        "escape_hatch": {
            "file": "escape_hatch/custom_scenes/incentive_flywheel.py",
            "class": "IncentiveFlywheelScene",
            "reason": "test",
        }
    })
    assert spec.class_name == "IncentiveFlywheelScene"
    assert spec.scene_path.is_file()


def test_parse_escape_hatch_missing_reason():
    with pytest.raises(ValueError, match="reason"):
        parse_escape_hatch({
            "escape_hatch": {
                "file": "escape_hatch/custom_scenes/incentive_flywheel.py",
                "class": "IncentiveFlywheelScene",
                "reason": "  ",
            }
        })


def test_guard_rejects_bad_import():
    with pytest.raises(GuardViolation, match="disallowed import"):
        lint_scene_file(_FIXTURES / "bad_import.py", "BadImportScene")


def test_guard_rejects_hex_literal():
    with pytest.raises(GuardViolation, match="hex color literal"):
        lint_scene_file(_FIXTURES / "bad_hex.py", "BadHexScene")


def test_guard_rejects_font_literal():
    with pytest.raises(GuardViolation, match="font name literal"):
        lint_scene_file(_FIXTURES / "bad_font.py", "BadFontScene")


def test_guard_rejects_bad_subclass():
    with pytest.raises(GuardViolation, match="must subclass EscapeHatchScene"):
        lint_scene_file(_FIXTURES / "bad_subclass.py", "BadSubclassScene")


def test_guard_accepts_incentive_flywheel():
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_scenes"
        / "incentive_flywheel.py"
    )
    lint_scene_file(path, "IncentiveFlywheelScene")

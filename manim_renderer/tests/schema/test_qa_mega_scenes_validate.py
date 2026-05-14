"""Smoke test — the four QA mega scenes pass the full validator (including
the new spatial dry-run tiers 4a/4b/4c). This catches future regressions
where a scene file would silently start producing overflow errors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manim_renderer.schema.validator import validate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCENES_DIR = _REPO_ROOT / "scripts" / "manim"

_QA_MEGA_SCENES = [
    "qa_mega_h.json",
    "qa_mega_v.json",
    "qa_mega_layouts_h.json",
    "qa_mega_layouts_v.json",
]


@pytest.mark.parametrize("scene_name", _QA_MEGA_SCENES)
def test_qa_mega_scene_validates(scene_name):
    path = _SCENES_DIR / scene_name
    assert path.exists(), f"QA mega scene missing: {path}"
    scene = json.loads(path.read_text())
    ok, errs = validate(scene)
    assert ok, errs


@pytest.mark.parametrize("scene_name", ["prisoners_dilemma.json", "prisoners_dilemma_vertical.json"])
def test_prisoners_dilemma_scenes_still_validate(scene_name):
    """Regression: the PD scenes — patched in PR A to fit — must continue
    to validate as Phase 1.5 changes accumulate."""
    path = _SCENES_DIR / scene_name
    scene = json.loads(path.read_text())
    ok, errs = validate(scene)
    assert ok, errs

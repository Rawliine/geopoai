"""PR Q — new QA scenes (qa_roles, qa_roles_v, qa_sequence) validate cleanly.

These exercise the Phase 2 surface end-to-end:
  * `qa_roles.json` / `qa_roles_v.json` — role transitions via setRole +
    subject-based callouts.
  * `qa_sequence.json` — showCalloutSequence with three callouts on a
    PayoffMatrix.

Validation must pass for every shipping scene; any [composition-fit] or
schema regression breaks Phase 2 content authoring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manim_renderer.schema.validator import validate

_SCENES = [
    "qa_roles.json",
    "qa_roles_v.json",
    "qa_sequence.json",
]


@pytest.mark.parametrize("name", _SCENES)
def test_qa_scene_validates(name):
    root = Path(__file__).resolve().parents[3] / "scripts" / "manim"
    path = root / name
    assert path.exists(), f"missing QA scene: {path}"
    scene = json.loads(path.read_text())
    ok, errs = validate(scene)
    assert ok, (name, errs)

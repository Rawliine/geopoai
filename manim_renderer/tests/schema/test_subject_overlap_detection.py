"""Validator catches subject-based callout overlap + overflow.

Step 3A: `check_anchor_overflows` and `check_collisions` now walk
`params.subject` (not just `params.anchor`). These tests pin that
behavior so it can't silently regress.
"""

from __future__ import annotations

from manim_renderer.schema.validator import validate


def _scene_with_subject_callout(callout_text: str, callout_width: float = 4.0):
    """A subject-anchored callout on a body StatBlock + a second StatBlock
    already at right-of:host. The callout, predicted to land right-of host
    or below, must not collide with the second stat or punch the frame."""
    return {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "title-body", "duration": 5},
        "slots": {
            "title": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "t", "text": "x", "size": "title"},
            },
            "body": {
                "at": 0.1,
                "action": "showStatBlock",
                "params": {
                    "id": "host",
                    "value": 100,
                    "label": "Host",
                    "size": "large",
                },
            },
        },
        "overlays": [
            {
                "at": 1.0,
                "action": "showCalloutBox",
                "params": {
                    "id": "c",
                    "text": callout_text,
                    "subject": "host",
                    "width": callout_width,
                },
            },
        ],
        "timeline": [],
    }


def test_subject_callout_in_room_validates():
    """Narrow callout on a large host has room on at least one side."""
    scene = _scene_with_subject_callout("short note", callout_width=3.0)
    ok, errs = validate(scene)
    assert ok, errs


def test_subject_callout_huge_overflows_frame():
    """An oversized callout on a hosted subject should be flagged — either
    as a frame overflow, anchor pollution, or collision with the title."""
    scene = _scene_with_subject_callout(
        "this is a very long callout " * 6, callout_width=8.0,
    )
    ok, errs = validate(scene)
    assert not ok
    assert any(
        "anchor-pollutes-frame" in e
        or "frame-overflow" in e
        or "collision-overlap" in e
        for e in errs
    ), errs


def test_subject_callout_overlap_with_other_anchored_stat_flagged():
    """Mirrors the qa_roles.json failure: subject callout collides with a
    second component anchored on the host's right."""
    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "title-body", "duration": 10},
        "slots": {
            "title": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {"id": "t", "text": "x", "size": "title"},
            },
            "body": {
                "at": 0.1,
                "action": "showStatBlock",
                "params": {
                    "id": "host", "value": 100, "label": "Host", "size": "large",
                },
            },
        },
        "overlays": [
            {"at": 1.0, "action": "showStatBlock",
             "params": {"id": "neighbor", "value": 50, "label": "N",
                        "size": "medium", "anchor": "right-of:host"}},
            {"at": 2.0, "action": "showCalloutBox",
             "params": {"id": "c", "text": "hi", "subject": "host",
                        "width": 4.0}},
        ],
        "timeline": [],
    }
    ok, errs = validate(scene)
    assert not ok
    assert any(
        "collision-overlap" in e or "anchor-pollutes-frame" in e
        for e in errs
    ), errs

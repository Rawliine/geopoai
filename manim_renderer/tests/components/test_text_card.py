"""Smoke test: TextCard renders to MP4 at preview quality."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_text_card_renders_horizontal(tmp_path):
    from pipeline.render_manim import render_manim_sync

    scene = {
        "renderer": "manim",
        "format": "horizontal",
        "quality": "preview",
        "scene": {"layout": "hero", "duration": 2, "theme": "dark"},
        "slots": {
            "main": {
                "at": 0.0,
                "action": "showTextCard",
                "params": {
                    "id": "smoke-test",
                    "text": "smoke",
                    "timing": "normal",
                    "effect": "fade-in",
                },
            }
        },
        "overlays": [],
        "timeline": [],
    }

    out = render_manim_sync(scene, "test_text_card_smoke")
    assert out.exists(), f"expected MP4 at {out}"
    assert out.stat().st_size > 0, "MP4 is empty"

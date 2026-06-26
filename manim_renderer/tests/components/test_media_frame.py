"""MediaFrame unit tests — contain math, construction, image + video."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from manim_renderer.components.media_frame import (
    MediaFrame,
    contain_fit,
    cover_fit,
)
from manim_renderer.components.narrative.image_card import ImageCard

logging.getLogger("manim").setLevel(logging.ERROR)

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_LANDSCAPE = "manim_renderer/assets/images/test_landscape.png"
_PORTRAIT = "manim_renderer/assets/images/test_portrait.png"
_VIDEO = "manim_renderer/assets/videos/test_clip.mp4"


# --- pure contain / cover math -----------------------------------------------

def test_contain_landscape_in_tall_box():
    w, h = contain_fit(16 / 9, inner_w=4.0, inner_h=6.0)
    assert abs(w - 4.0) < 1e-6
    assert abs(h - 4.0 / (16 / 9)) < 1e-3
    assert h < 6.0


def test_contain_portrait_in_wide_box():
    w, h = contain_fit(9 / 16, inner_w=6.0, inner_h=4.0)
    assert abs(h - 4.0) < 1e-6
    assert w < 6.0
    assert abs(w / h - 9 / 16) < 1e-3


def test_cover_fills_inner_box():
    w, h = cover_fit(16 / 9, inner_w=4.0, inner_h=4.0)
    assert w >= 4.0 - 1e-6 and h >= 4.0 - 1e-6


# --- construction ------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
@pytest.mark.parametrize("src,aspect_key", [
    (_LANDSCAPE, "landscape"),
    (_PORTRAIT, "portrait"),
])
def test_image_contain_builds(fmt, src, aspect_key):
    mf = MediaFrame(
        {"id": f"img-{aspect_key}", "src": src, "fit": "contain", "size": "medium"},
        format=fmt,
    )
    assert mf.width > 0 and mf.height > 0
    assert hasattr(mf, "_media")
    assert hasattr(mf, "_letterbox")


@pytest.mark.parametrize("fmt", ["horizontal", "vertical"])
def test_video_contain_builds(fmt):
    mf = MediaFrame(
        {"id": "vid", "src": _VIDEO, "fit": "contain", "size": "medium"},
        format=fmt,
    )
    assert mf.width > 0
    assert mf._media.__class__.__name__ == "_VideoImageMobject"


def test_image_card_alias_ken_burns():
    ic = ImageCard(
        {
            "id": "legacy",
            "image": _LANDSCAPE,
            "source": "Test credit",
            "size": "medium",
        },
        format="horizontal",
    )
    assert ic.params.get("ken_burns") is True
    assert ic.width > 0


def test_requires_src():
    with pytest.raises(ValueError, match="src"):
        MediaFrame({"id": "x"}, format="horizontal")


def test_unknown_src_raises():
    with pytest.raises(ValueError, match="not found"):
        MediaFrame({"id": "x", "src": "no_such_file.png"}, format="horizontal")

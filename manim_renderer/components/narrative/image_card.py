"""ImageCard — backward-compatible alias for MediaFrame with Ken Burns on.

``showImageCard`` keeps working: ``image`` → ``src``, ``source`` → ``attribution``,
Ken Burns enabled by default. New scenes should prefer ``showMedia``.
"""

from __future__ import annotations

from manim_renderer.components.media_frame import MediaFrame


def _map_image_card_params(params: dict) -> dict:
    p = dict(params)
    if "image" in p and "src" not in p:
        p["src"] = p["image"]
    if "source" in p and "attribution" not in p:
        p["attribution"] = p["source"]
    p.setdefault("ken_burns", True)
    p.setdefault("direction", "in")
    return p


class ImageCard(MediaFrame):
    """Framed raster + Ken Burns drift + mandatory attribution chip."""

    def __init__(self, params: dict, format: str = "horizontal", **kwargs):
        mapped = _map_image_card_params(params)
        if "source" not in params and "attribution" not in mapped:
            raise ValueError(
                "ImageCard requires params.source (attribution credit text)"
            )
        super().__init__(mapped, format=format, **kwargs)

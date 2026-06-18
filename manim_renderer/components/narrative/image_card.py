"""ImageCard — a framed raster image with a slow Ken Burns drift + credit chip.

Manim's `ImageMobject` is NOT a `VMobject`, so this component subclasses
`Group` (not `VGroup`/`BaseComponent`) and mirrors the small component contract
the runner needs (id/role/build/entrance/anchors/measure). The Group holds the
image, an opaque "matte" that hides the Ken Burns overscan, a rounded frame
border, and a small attribution chip.

Params:
  * ``image``  (required) — path to the raster. Resolved absolute, repo-root
                relative, or as a bare name under repo-root ``assets/images/``
                (the convention for episode-supplied images).
  * ``source`` (required) — attribution / credit text, rendered as a small chip
                in the corner at the caption type size. Every image is credited.
  * ``width`` / ``height`` — frame size in Manim units. If only one is given the
                other follows the image aspect; default keeps the image aspect.
  * ``zoom``      — Ken Burns punch amount (fraction, default 0.08).
  * ``direction`` — drift direction: in | out | left | right | up | down
                (default ``in`` = pure slow zoom). The motion is continuous and
                ping-pongs, so the card is NEVER static.
  * ``mask``      — ``country:<name>`` is accepted but deferred to the map side;
                here the frame is always rectangular / rounded.
"""

from __future__ import annotations

from pathlib import Path

from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP,
    Group, ImageMobject, RoundedRectangle, Text, VGroup,
)

from manim_renderer.layouts.base import ROLE_SCALE
from manim_renderer.theme.palette import UI
from manim_renderer.theme.spacing import text_height_units
from manim_renderer.theme.typography import FONTS, FONT_SCALE

_REPO_ROOT = Path(__file__).resolve().parents[3]

_FRAME_STROKE = 2.0
_FRAME_CORNER = 0.12
_DEFAULT_ZOOM = 0.08
_KB_PERIOD_S = 14.0           # ping-pong period of the drift
_CHIP_PAD = 0.12              # chip padding + inset from the frame corner

_PAN = {
    "in": ORIGIN, "out": ORIGIN,
    "left": LEFT, "right": RIGHT, "up": UP, "down": DOWN,
}

# Default frame heights (Manim units) by size role, per format.
_SIZE_HEIGHT = {
    "horizontal": {"small": 3.0, "medium": 4.5, "large": 6.0},
    "vertical":   {"small": 4.0, "medium": 6.0, "large": 8.0},
}
_DEFAULT_ASPECT = 16 / 9


def _resolve_image_path(image: str) -> Path:
    """Resolve `image` as absolute, repo-root-relative, or assets/images/<name>."""
    p = Path(image)
    if p.is_absolute() and p.exists():
        return p
    for cand in (_REPO_ROOT / image, _REPO_ROOT / "assets" / "images" / image):
        if cand.exists():
            return cand
    raise ValueError(
        f"ImageCard image {image!r} not found (looked at {image}, "
        f"{_REPO_ROOT / image}, and assets/images/{image}). Episode images go "
        f"under assets/images/."
    )


class ImageCard(Group):
    """Framed raster + Ken Burns drift + attribution chip."""

    SIZE_KIND = "default"
    DEFAULT_ROLE = "primary"

    def __init__(self, params: dict, format: str = "horizontal", **kwargs):
        super().__init__(**kwargs)
        self.params = params
        self.format = format
        self.id = params.get("id")
        self.role = params.get("role", self.DEFAULT_ROLE)
        self._kb_t = 0.0
        self.build()

    # --- sizing (consumed by the validator + solver) -------------------------

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        h = cls._frame_height(params, format)
        w = float(params.get("width", h * _DEFAULT_ASPECT))
        return (w, h)

    @classmethod
    def preferred_size(cls, params, format, role="primary") -> tuple[float, float]:
        if role not in ROLE_SCALE:
            raise ValueError(f"preferred_size: unknown role {role!r}")
        scale = ROLE_SCALE[role]
        if scale == 0.0:
            return (0.0, 0.0)
        w, h = cls.measure(params, format)
        return (w * scale, h * scale)

    @staticmethod
    def _frame_height(params: dict, format: str) -> float:
        if params.get("height") is not None:
            return float(params["height"])
        size = params.get("size", "medium")
        table = _SIZE_HEIGHT.get(format, _SIZE_HEIGHT["horizontal"])
        return table.get(size, table["medium"])

    # --- build ---------------------------------------------------------------

    def build(self) -> None:
        p = self.params
        if "image" not in p:
            raise ValueError("ImageCard requires params.image (a raster path)")
        if "source" not in p:
            raise ValueError(
                "ImageCard requires params.source (attribution credit text)"
            )

        img_path = _resolve_image_path(str(p["image"]))
        image = ImageMobject(str(img_path))
        self._aspect = float(image.width) / float(image.height or 1.0)

        # Frame size: explicit, else size-role height with the image's aspect.
        fh = self._frame_height(p, self.format)
        fw = float(p.get("width", fh * self._aspect))
        self._frame_w, self._frame_h = fw, fh
        self._zoom = float(p.get("zoom", _DEFAULT_ZOOM))
        self._pan_vec = _PAN.get(p.get("direction", "in"), ORIGIN)

        # Image scaled to COVER the frame (then Ken Burns punches in from there).
        image.scale_to_fit_width(max(fw, fh * self._aspect))
        image.move_to(ORIGIN)
        self.add(image)
        self._image = image

        # Matte: opaque background ring that hides Ken Burns overscan so the
        # image never bleeds past the frame. Bounded by the max drift.
        self._matte_margin = self._zoom * max(fw, fh) + 0.25 * max(fw, fh)
        for rect in self._build_matte(fw, fh, self._matte_margin):
            self.add(rect)

        # Rounded frame border on top of the matte.
        self._frame = RoundedRectangle(
            width=fw, height=fh, corner_radius=_FRAME_CORNER,
            stroke_color=UI["border"], stroke_width=_FRAME_STROKE,
            fill_opacity=0.0,
        )
        self.add(self._frame)

        # Mandatory attribution chip, bottom-right inside the frame.
        self.add(self._build_chip(str(p["source"]), fw, fh))

        self.move_to(ORIGIN)
        # Continuous Ken Burns — runs every frame (incl. waits) so it's never static.
        self.add_updater(self._ken_burns)

    def _build_matte(self, fw: float, fh: float, m: float):
        bg = UI["background"]
        hw, hh = fw / 2.0, fh / 2.0
        # top, bottom, left, right opaque background rectangles around the window.
        specs = [
            (fw + 2 * m, m, 0.0, hh + m / 2.0),
            (fw + 2 * m, m, 0.0, -hh - m / 2.0),
            (m, fh, -hw - m / 2.0, 0.0),
            (m, fh, hw + m / 2.0, 0.0),
        ]
        rects = []
        for w, h, cx, cy in specs:
            r = RoundedRectangle(
                width=w, height=h, corner_radius=0.0,
                stroke_width=0.0, fill_color=bg, fill_opacity=1.0,
            )
            r.move_to([cx, cy, 0.0])
            rects.append(r)
        return rects

    def _build_chip(self, source: str, fw: float, fh: float) -> VGroup:
        cap = FONT_SCALE[self.format]["caption"]
        label = Text(source, font=FONTS["primary"], font_size=int(cap * 0.8))
        label.set_color(UI["text_primary"])
        bg = RoundedRectangle(
            width=label.width + 2 * _CHIP_PAD,
            height=label.height + 1.4 * _CHIP_PAD,
            corner_radius=0.06,
            stroke_width=0.0, fill_color=UI["surface"], fill_opacity=0.72,
        )
        chip = VGroup(bg, label)
        label.move_to(bg.get_center())
        # Bottom-right, inset just inside the frame border.
        chip.move_to([
            fw / 2.0 - bg.width / 2.0 - _CHIP_PAD,
            -fh / 2.0 + bg.height / 2.0 + _CHIP_PAD,
            0.0,
        ])
        self._chip = chip
        return chip

    # --- Ken Burns updater ---------------------------------------------------

    def _ken_burns(self, _mob, dt: float) -> None:
        self._kb_t += dt
        phase = (self._kb_t % _KB_PERIOD_S) / _KB_PERIOD_S
        tri = 1.0 - abs(2.0 * phase - 1.0)  # 0 → 1 → 0
        # Track the live frame so the drift composes with any card move/scale.
        fw = float(self._frame.width)
        fh = float(self._frame.height)
        cover = max(fw, fh * self._aspect)
        self._image.scale_to_fit_width(cover * (1.0 + self._zoom * tri))
        pan = self._pan_vec * (0.12 * fw * tri)
        self._image.move_to(self._frame.get_center() + pan)

    # --- component contract (mirrors BaseComponent) --------------------------

    def entrance(self, effect: str, timing: str, **extra):
        from manim_renderer.effects.entrances import get_entrance
        return get_entrance(effect, self, timing, **extra)

    def exit(self, effect: str = "fade-out", timing: str = "fast", **extra):
        from manim_renderer.effects.exits import get_exit
        return get_exit(effect, self, timing, **extra)

    def extra_id_registrations(self) -> dict:
        return {}

    def position_finalized(self, *, anchor=None, target=None, format="horizontal"):
        return None

    def reposition(self, *, host_mob=None, format="horizontal"):
        return None

    # Standard anchors so callouts can target an image card.
    def get_anchor(self, name: str):
        import numpy as np
        token = name.partition(":")[0].replace("-", "_")
        method = getattr(self, f"_get_anchor_{token}", None)
        if method is None:
            raise KeyError(f"ImageCard has no anchor {name!r}")
        return np.asarray(method(), dtype=float)

    def _get_anchor_top(self): return self.get_top()
    def _get_anchor_bottom(self): return self.get_bottom()
    def _get_anchor_left(self): return self.get_left()
    def _get_anchor_right(self): return self.get_right()
    def _get_anchor_center(self): return self.get_center()
    def _get_anchor_top_left(self): return self.get_corner((-1, 1, 0))
    def _get_anchor_top_right(self): return self.get_corner((1, 1, 0))
    def _get_anchor_bottom_left(self): return self.get_corner((-1, -1, 0))
    def _get_anchor_bottom_right(self): return self.get_corner((1, -1, 0))

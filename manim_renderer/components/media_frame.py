"""MediaFrame — fitted image/video box (object-fit: contain) with optional caption.

A layout-sized frame displays raster images or short video clips scaled to fit
inside without stretching. Letterbox bars use token colors; border, padding, and
chip styling come from ``theme.media``. Optional Ken Burns drift (opt-in) and
attribution chip reuse the ImageCard behavior.

Params:
  * ``src`` (required) — path to image or video (absolute, repo-root relative,
                or bare name under ``assets/images/`` / ``assets/videos/``).
  * ``fit`` — ``contain`` (default, letterboxed) or ``cover`` (fill + matte crop).
  * ``caption`` — optional line below the frame.
  * ``attribution`` — optional credit chip inside the frame (bottom-right).
  * ``ken_burns`` — bool; slow pan/zoom when true (default false for showMedia).
  * ``direction`` / ``zoom`` — Ken Burns controls (when ``ken_burns`` is true).
  * ``media_type`` — ``auto`` | ``image`` | ``video`` (extension override).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP,
    Group, ImageMobject, Rectangle, RoundedRectangle, Text, VGroup,
)
from manim.utils.images import change_to_rgba_array

from manim_renderer.layouts.base import ROLE_SCALE
from manim_renderer.theme.media import (
    FRAME_HEIGHT,
    _DEFAULT_ASPECT,
    chip_fill_color,
    chip_text_color,
    frame_border_color,
    is_video_path,
    letterbox_color,
    media_metric,
)
from manim_renderer.theme.typography import FONTS, FONT_SCALE

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PAN = {
    "in": ORIGIN, "out": ORIGIN,
    "left": LEFT, "right": RIGHT, "up": UP, "down": DOWN,
}


def _resolve_media_path(src: str) -> Path:
    """Resolve ``src`` as absolute, repo-root-relative, or under assets/."""
    p = Path(src)
    if p.is_absolute() and p.exists():
        return p
    candidates = (
        _REPO_ROOT / src,
        _REPO_ROOT / "assets" / "images" / src,
        _REPO_ROOT / "assets" / "videos" / src,
        _REPO_ROOT / "manim_renderer" / "assets" / "images" / src,
        _REPO_ROOT / "manim_renderer" / "assets" / "videos" / src,
    )
    for cand in candidates:
        if cand.exists():
            return cand
    raise ValueError(
        f"MediaFrame src {src!r} not found (tried {src}, assets/images/, "
        f"assets/videos/). Episode media goes under assets/."
    )


def contain_fit(
    media_aspect: float,
    inner_w: float,
    inner_h: float,
) -> tuple[float, float]:
    """Return (width, height) to fit ``media_aspect`` inside inner box."""
    if media_aspect <= 0:
        return (inner_w, inner_h)
    box_aspect = inner_w / inner_h
    if media_aspect > box_aspect:
        w = inner_w
        h = inner_w / media_aspect
    else:
        h = inner_h
        w = inner_h * media_aspect
    return (w, h)


def cover_fit(
    media_aspect: float,
    inner_w: float,
    inner_h: float,
) -> tuple[float, float]:
    """Return (width, height) to cover inner box (may exceed on one axis)."""
    if media_aspect <= 0:
        return (inner_w, inner_h)
    box_aspect = inner_w / inner_h
    if media_aspect > box_aspect:
        h = inner_h
        w = inner_h * media_aspect
    else:
        w = inner_w
        h = inner_w / media_aspect
    return (w, h)


def _load_video_frames(path: Path) -> tuple[list[np.ndarray], float]:
    """Decode all frames up front — keeps mobjects deepcopy-safe for FadeIn."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"MediaFrame cannot open video {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    frames: list[np.ndarray] = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA))
    cap.release()
    if not frames:
        raise ValueError(f"MediaFrame video has no frames: {path}")
    return frames, fps


class _VideoImageMobject(ImageMobject):
    """ImageMobject whose pixels advance with scene time (deterministic stepping)."""

    def __init__(self, frames: list[np.ndarray], fps: float, **kwargs):
        self._frames = frames
        self._fps = fps
        self._video_t = 0.0
        self._duration = len(frames) / fps
        super().__init__(frames[0], **kwargs)

    def advance(self, dt: float) -> None:
        self._video_t = (self._video_t + dt) % max(self._duration, 1e-6)
        idx = int(self._video_t * self._fps) % len(self._frames)
        self.pixel_array = change_to_rgba_array(
            self._frames[idx], self.pixel_array_dtype,
        )


class MediaFrame(Group):
    """Fitted media box — contain letterbox by default, optional Ken Burns."""

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

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        fw, fh = cls._measure_dims(params, format)
        h_extra = 0.0
        if params.get("caption"):
            cap = FONT_SCALE.get(format, FONT_SCALE["horizontal"])["caption"]
            h_extra = cap * 0.0104 + media_metric("caption_gap", format)
        return (fw, fh + h_extra)

    @classmethod
    def preferred_size(cls, params, format, role="primary") -> tuple[float, float]:
        if role not in ROLE_SCALE:
            raise ValueError(f"preferred_size: unknown role {role!r}")
        scale = ROLE_SCALE[role]
        if scale == 0.0:
            return (0.0, 0.0)
        w, h = cls.measure(params, format)
        return (w * scale, h * scale)

    @classmethod
    def _measure_dims(cls, params: dict, format: str) -> tuple[float, float]:
        """Conservative (w, h) for validator slot-fit — no image load."""
        fh = cls._frame_height(params, format)
        default_aspect = 9 / 16 if format == "vertical" else _DEFAULT_ASPECT
        fw = float(params.get("width", fh * default_aspect))
        return (fw, fh)

    @classmethod
    def _frame_dims(cls, params: dict, format: str) -> tuple[float, float]:
        fh = cls._frame_height(params, format)
        aspect = float(params.get("_aspect_override", _DEFAULT_ASPECT))
        fw = float(params.get("width", fh * aspect))
        return (fw, fh)

    @staticmethod
    def _frame_height(params: dict, format: str) -> float:
        if params.get("height") is not None:
            return float(params["height"])
        size = params.get("size", "medium")
        table = FRAME_HEIGHT.get(format, FRAME_HEIGHT["horizontal"])
        return table.get(size, table["medium"])

    def build(self) -> None:
        p = self.params
        src_key = "src" if "src" in p else "image"
        if src_key not in p:
            raise ValueError("MediaFrame requires params.src (image or video path)")
        media_path = _resolve_media_path(str(p[src_key]))
        media_type = p.get("media_type", "auto")
        is_video = (
            media_type == "video"
            or (media_type == "auto" and is_video_path(str(media_path)))
        )

        if is_video:
            frames, _vfps = _load_video_frames(media_path)
            media = _VideoImageMobject(frames, _vfps)
            self._aspect = float(frames[0].shape[1]) / float(frames[0].shape[0] or 1)
        else:
            media = ImageMobject(str(media_path))
            self._aspect = float(media.width) / float(media.height or 1.0)

        fmt = self.format
        slot_bounds = p.get("_slot_bounds")
        if slot_bounds and p.get("width") is None and p.get("height") is None:
            sw, sh = float(slot_bounds[0]), float(slot_bounds[1])
            fh = min(self._frame_height(p, fmt), sh)
            fw = min(fh * self._aspect, sw)
        else:
            fh = self._frame_height(p, fmt)
            fw = float(p.get("width", fh * self._aspect))
        self._frame_w, self._frame_h = fw, fh
        pad = media_metric("padding", fmt)
        stroke = media_metric("frame_stroke", fmt)
        corner = media_metric("corner_radius", fmt)
        inner_w, inner_h = max(fw - 2 * pad, 0.1), max(fh - 2 * pad, 0.1)

        fit = p.get("fit", "contain")
        if fit == "cover":
            mw, mh = cover_fit(self._aspect, inner_w, inner_h)
        else:
            mw, mh = contain_fit(self._aspect, inner_w, inner_h)

        media.scale_to_fit_width(mw)
        if abs(media.height - mh) > 1e-3:
            media.scale_to_fit_height(mh)
        media.move_to(ORIGIN)

        # Letterbox fill behind the media (visible when aspect differs).
        letterbox = Rectangle(
            width=inner_w, height=inner_h,
            stroke_width=0.0,
            fill_color=letterbox_color(), fill_opacity=1.0,
        )
        self.add(letterbox)
        self._letterbox = letterbox

        self.add(media)
        self._media = media

        ken_burns = bool(p.get("ken_burns", False))
        if ken_burns:
            self._zoom = float(p.get("zoom", media_metric("ken_burns_zoom_default", fmt)))
            self._pan_vec = _PAN.get(p.get("direction", "in"), ORIGIN)
            matte_extra = media_metric("ken_burns_matte_extra", fmt)
            self._matte_margin = self._zoom * max(fw, fh) + matte_extra * max(fw, fh)
            for rect in self._build_matte(fw, fh, self._matte_margin):
                self.add(rect)

        self._frame = RoundedRectangle(
            width=fw, height=fh, corner_radius=corner,
            stroke_color=frame_border_color(), stroke_width=stroke,
            fill_opacity=0.0,
        )
        self.add(self._frame)

        attribution = p.get("attribution") or p.get("source")
        if attribution:
            self.add(self._build_chip(str(attribution), fw, fh, fmt))

        caption = p.get("caption")
        if caption:
            cap_size = FONT_SCALE[fmt]["caption"]
            cap_text = Text(
                str(caption), font=FONTS["primary"], font_size=int(cap_size),
            )
            cap_text.set_color(chip_text_color())
            cap_text.move_to([0.0, -fh / 2.0 - media_metric("caption_gap", fmt), 0.0])
            self.add(cap_text)
            self._caption_mob = cap_text

        self.move_to(ORIGIN)

        if is_video:
            self.add_updater(self._video_tick)
        if ken_burns:
            self.add_updater(self._ken_burns)

    def _build_matte(self, fw: float, fh: float, m: float):
        bg = letterbox_color()
        hw, hh = fw / 2.0, fh / 2.0
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

    def _build_chip(self, source: str, fw: float, fh: float, fmt: str) -> VGroup:
        chip_pad = media_metric("chip_pad", fmt)
        chip_corner = media_metric("chip_corner", fmt)
        cap = FONT_SCALE[fmt]["caption"]
        label = Text(source, font=FONTS["primary"], font_size=int(cap * 0.8))
        label.set_color(chip_text_color())
        bg = RoundedRectangle(
            width=label.width + 2 * chip_pad,
            height=label.height + 1.4 * chip_pad,
            corner_radius=chip_corner,
            stroke_width=0.0, fill_color=chip_fill_color(), fill_opacity=0.72,
        )
        chip = VGroup(bg, label)
        label.move_to(bg.get_center())
        chip.move_to([
            fw / 2.0 - bg.width / 2.0 - chip_pad,
            -fh / 2.0 + bg.height / 2.0 + chip_pad,
            0.0,
        ])
        self._chip = chip
        return chip

    def _video_tick(self, _mob, dt: float) -> None:
        if isinstance(self._media, _VideoImageMobject):
            self._media.advance(dt)

    def _ken_burns(self, _mob, dt: float) -> None:
        self._kb_t += dt
        period = media_metric("ken_burns_period_s", self.format)
        phase = (self._kb_t % period) / period
        tri = 1.0 - abs(2.0 * phase - 1.0)
        fw = float(self._frame.width)
        fh = float(self._frame.height)
        pad = media_metric("padding", self.format)
        inner_w, inner_h = max(fw - 2 * pad, 0.1), max(fh - 2 * pad, 0.1)
        fit = self.params.get("fit", "contain")
        if fit == "cover":
            base_w, base_h = cover_fit(self._aspect, inner_w, inner_h)
        else:
            base_w, base_h = contain_fit(self._aspect, inner_w, inner_h)
        self._media.scale_to_fit_width(base_w * (1.0 + self._zoom * tri))
        pan_frac = media_metric("ken_burns_pan_frac", self.format)
        pan = self._pan_vec * (pan_frac * fw * tri)
        self._media.move_to(self._frame.get_center() + pan)

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

    def get_anchor(self, name: str):
        token = name.partition(":")[0].replace("-", "_")
        method = getattr(self, f"_get_anchor_{token}", None)
        if method is None:
            raise KeyError(f"MediaFrame has no anchor {name!r}")
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

"""CalloutBox — text bubble + leader line to an anchor target.

Phase 1.5: four visual styles via the `style` param — `neon` (default),
`card`, `glass`, `bracket`. Style spec dispatch lives in `_callout_styles.py`;
this module handles text construction, leader-line geometry, and custom
anchors. Style controls only the bubble's visual rendering + the bubble's
entrance/exit animation. Leader line is style-agnostic.

The first component to use the anchor resolver and the `position_finalized`
hook. The bubble is positioned at the anchor coord; the leader line is added
in `position_finalized` once the absolute coords are known.

Why two-phase positioning: the leader line's endpoint is in the *target's*
absolute coordinate space (e.g. the right edge of a matrix). At `build()`
time the bubble is at origin; only after `move_to(coord)` do we know where
the bubble's edge is relative to the target. `position_finalized` fires
between move_to and entrance, which is the correct seam.

Custom anchors:
  * `head` — leader tip (= position on target)
  * `tail` — leader root (= bubble edge nearest target)
  * Standard 9 inherited from BaseComponent

Style param (Phase 1.5):
  * `neon`    (default) — accent stroke traces in, text fades after; on
                          exit text fades, border erases via Uncreate.
  * `card`              — surface fill + thin border, fades together.
  * `glass`             — translucent dark fill + accent border, fades together.
  * `bracket`           — left-edge accent bar + text, no rectangle.

Effects:
  Each style ships a signature entrance/exit. The legacy per-effect dispatch
  (fade-in, grow-up, etc.) is retained but treated as a fallback override
  when the explicit `effect` param differs from the style's default.
"""

from __future__ import annotations

import numpy as np
from manim import (
    Arrow,
    Line,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.components.narrative._callout_styles import (
    CALLOUT_STYLES,
    get_style,
)
from manim_renderer.resolvers.anchor import parse_anchor
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI, pick_text_color
from manim_renderer.theme.timing import TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


# Visual defaults shared with `_callout_styles.py`.
_BUBBLE_PADDING_X = 0.35
_BUBBLE_PADDING_Y = 0.20
_LEADER_STROKE = 2.0
_DEFAULT_STYLE = "neon"
_DEFAULT_ACCENT_KEY = "highlight"


# Maps anchor token -> (bubble_edge_method_name, target_edge_method_name).
# After format auto-flip in resolve_anchor, the bubble is positioned correctly
# but we need the right edges for the leader line. We re-parse the original
# anchor string in position_finalized and respect the format flip there too.
_LEADER_EDGES_HORIZONTAL = {
    "above":    ("get_bottom", "get_top"),
    "below":    ("get_top",    "get_bottom"),
    "left-of":  ("get_right",  "get_left"),
    "right-of": ("get_left",   "get_right"),
    "inside":   ("get_center", "get_center"),  # zero-length, leader hidden
}

# Vertical-format flip mirrors resolve_anchor's flip.
_VERTICAL_FLIP_TOKEN = {"right-of": "below", "left-of": "above"}


class CalloutBox(BaseComponent):
    """Text bubble + leader line to a target component."""

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        """Estimate from text length + max width + padding. Wraps lines that
        exceed `width` (default 4.0). Char width estimate is conservative —
        the validator's slot-fit check tolerates some slack."""
        text = str(params.get("text", ""))
        max_w = float(params.get("width", 4.0))
        caption_size = FONT_SCALE[format]["caption"]
        char_w = caption_size / 130.0
        line_h = caption_size / 70.0  # caption lines a bit taller relative to chars

        text_width = max(len(text), 1) * char_w
        if text_width <= max_w:
            lines = 1
            line_width = text_width
        else:
            lines = max(1, int(text_width / max_w) + 1)
            line_width = max_w

        bubble_w = line_width + 2 * _BUBBLE_PADDING_X
        bubble_h = lines * line_h + (lines - 1) * 0.1 + 2 * _BUBBLE_PADDING_Y
        return (bubble_w, bubble_h)

    def build(self) -> None:
        p = self.params

        if "text" not in p:
            raise ValueError("CalloutBox requires params.text")
        # `anchor` is REQUIRED for a callout — without it there's no leader
        # and you might as well use a TextCard. Schema enforces it too.
        if "anchor" not in p:
            raise ValueError(
                "CalloutBox requires params.anchor (anchor string like "
                "'below:matrix-1'); without one, use TextCard instead."
            )

        self._text_str = str(p["text"])
        self._max_width = float(p.get("width", 4.0))
        self._draw_arrow = bool(p.get("arrow", True))
        self._color_key = p.get("color")  # palette key or None

        # Style dispatch (Phase 1.5).
        style_name = p.get("style", _DEFAULT_STYLE)
        if style_name not in CALLOUT_STYLES:
            raise ValueError(
                f"CalloutBox style {style_name!r} unknown; "
                f"available: {sorted(CALLOUT_STYLES)}"
            )
        self._style_spec = get_style(style_name)
        self._style_name = style_name

        # Build the bubble at origin via the chosen style.
        self._build_bubble()

        # Leader is added in position_finalized after we know absolute coords.
        # Initialize to None so anchor lookups can detect "no leader yet".
        self._leader_mob = None
        self._leader_endpoints: tuple[np.ndarray, np.ndarray] | None = None

    # --- bubble construction -------------------------------------------------

    @staticmethod
    def _resolve_accent_hex(color_key: str | None) -> str:
        """Resolve `color` param to a hex accent (the stroke / bar color).

        Default: SEMANTIC['highlight']. Accepts any ACTOR / SEMANTIC / UI key.
        Hex strings or unknown keys raise.
        """
        if color_key is None:
            return SEMANTIC[_DEFAULT_ACCENT_KEY]
        palette = {**ACTORS, **SEMANTIC, **UI}
        if color_key not in palette:
            raise ValueError(
                f"CalloutBox color must be a palette key; got {color_key!r}; "
                f"available: {sorted(palette)}"
            )
        return palette[color_key]

    def _build_bubble(self) -> None:
        accent_hex = self._resolve_accent_hex(self._color_key)
        self._accent_hex = accent_hex

        # Text color: for `card` (filled background), explicit color key wins
        # but defaults to text_primary. For other styles (transparent bg),
        # auto-contrast against the scene background.
        if self._style_name == "card":
            text_color = UI["text_primary"]
        else:
            text_color = pick_text_color(UI["background"])

        # Build the text first to size the bubble around it.
        # Note: Manim's Text(color=hex) doesn't reliably apply hex strings —
        # use set_color() afterward instead. Same pattern in _wrap_text.
        self._text_mob = Text(
            self._text_str,
            font=FONTS["primary"],
            font_size=FONT_SCALE[self.format]["caption"],
        )
        self._text_mob.set_color(text_color)
        # Wrap text if it exceeds max_width — Manim's Text doesn't auto-wrap.
        if self._text_mob.width > self._max_width:
            self._text_mob = self._wrap_text(text_color)

        # Style dispatch: produce the bubble VGroup.
        self._bubble_mob = self._style_spec.build_bubble(
            self._text_mob, accent_hex, self.format,
        )

        # Order: bubble first so text renders on top of any filled background.
        # For `bracket` the bubble is a left-side bar — text doesn't overlap it.
        self.add(self._bubble_mob, self._text_mob)
        self._text_mob.move_to(self._bubble_mob.get_center())
        # For bracket style, the bar's center sits off-center of the bubble
        # group; reposition text to the right of the bar so they read together.
        if self._style_name == "bracket":
            self._text_mob.move_to(self._bubble_mob.get_right() + np.array([
                self._text_mob.width / 2 + _BUBBLE_PADDING_X,
                0.0, 0.0,
            ]))

    def _wrap_text(self, text_color: str) -> Text:
        """Naive word-wrap: break the string into lines that fit within
        max_width when rendered, then rebuild as a single Text with newlines."""
        words = self._text_str.split()
        lines: list[str] = []
        current: list[str] = []
        for w in words:
            trial = " ".join(current + [w])
            probe = Text(
                trial,
                font=FONTS["primary"],
                font_size=FONT_SCALE[self.format]["caption"],
            )
            if probe.width <= self._max_width or not current:
                current.append(w)
            else:
                lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        wrapped = Text(
            "\n".join(lines),
            font=FONTS["primary"],
            font_size=FONT_SCALE[self.format]["caption"],
            line_spacing=0.85,
        )
        wrapped.set_color(text_color)
        return wrapped

    # --- post-positioning: add the leader line -------------------------------

    def position_finalized(self, *, anchor=None, target=None, format="horizontal"):
        if anchor is None or target is None:
            return  # no leader if no anchor target
        token, _ = parse_anchor(anchor)

        # Apply the same format flip as resolve_anchor so leader edges match
        # the bubble's actual placement.
        if format == "vertical":
            token = _VERTICAL_FLIP_TOKEN.get(token, token)

        edges = _LEADER_EDGES_HORIZONTAL.get(token)
        if edges is None:
            return  # unknown token — no leader (defensive)

        bubble_edge_method, target_edge_method = edges
        bubble_pt = getattr(self._bubble_mob, bubble_edge_method)()
        target_pt = getattr(target, target_edge_method)()

        if token == "inside":
            self._leader_endpoints = None
            return  # bubble overlays target — no leader

        self._leader_endpoints = (np.asarray(bubble_pt), np.asarray(target_pt))

        leader_color = UI["text_secondary"]
        if self._draw_arrow:
            self._leader_mob = Arrow(
                start=bubble_pt,
                end=target_pt,
                color=leader_color,
                stroke_width=_LEADER_STROKE,
                buff=0.05,
                max_tip_length_to_length_ratio=0.15,
            )
        else:
            self._leader_mob = Line(
                start=bubble_pt,
                end=target_pt,
                color=leader_color,
                stroke_width=_LEADER_STROKE,
            )
        self.add(self._leader_mob)

    # --- bespoke entrance + exit: style dispatch + leader ------------------

    def entrance(self, effect: str, timing: str, **extra):
        # Style spec drives bubble + text animation. The explicit `effect`
        # param is honored when it's a generic entrance — it overrides the
        # style's signature animation. Otherwise the style's default fires.
        if effect in ("fade-in", "grow-up", "grow-down", "slide-left",
                      "slide-right", "slide-up", "slide-down", "write-in"):
            from manim_renderer.effects.entrances import get_entrance
            bubble_text_group = VGroup(self._bubble_mob, self._text_mob)
            bubble_anim = get_entrance(effect, bubble_text_group, timing, **extra)
        else:
            bubble_anim = self._style_spec.entrance(
                self._bubble_mob, self._text_mob, timing, **extra
            )

        if self._leader_mob is None:
            return bubble_anim

        from manim import Create, Succession
        leader_anim = Create(self._leader_mob, run_time=TIMING["fast"])
        return Succession(bubble_anim, leader_anim)

    def exit(self, effect: str = "fade-out", timing: str = "fast", **extra):
        """Style-driven exit. Explicit `effect=fade-out|dissolve` overrides
        the style's signature exit so authors can force a uniform fade across
        a scene when needed."""
        if effect in ("fade-out", "dissolve"):
            return super().exit(effect, timing, **extra)
        return self._style_spec.exit(
            self._bubble_mob, self._text_mob, timing, **extra
        )

    # --- custom anchors ------------------------------------------------------

    def _get_anchor_head(self) -> np.ndarray:
        """Tip of the leader (target side). Raises if no leader was drawn."""
        if self._leader_endpoints is None:
            raise KeyError(
                "CalloutBox `head` anchor unavailable — no leader was drawn "
                "(either anchor=inside:* or no anchor target was found)"
            )
        return self._leader_endpoints[1]

    def _get_anchor_tail(self) -> np.ndarray:
        """Root of the leader (bubble side). Raises if no leader was drawn."""
        if self._leader_endpoints is None:
            raise KeyError(
                "CalloutBox `tail` anchor unavailable — no leader was drawn"
            )
        return self._leader_endpoints[0]

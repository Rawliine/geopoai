"""CalloutBox — text bubble + leader line to an anchor target.

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

Effects:
  * fade-in (default) — bubble fades in then leader draws (Succession)
  * grow-up / grow-down — bubble grows then leader draws
  * Inherited entrances also work but the leader will animate in parallel
    with the bubble unless overridden.
"""

from __future__ import annotations

import numpy as np
from manim import (
    Arrow,
    Create,
    FadeIn,
    Line,
    RoundedRectangle,
    Succession,
    Text,
    VGroup,
)

from manim_renderer.components.base import BaseComponent
from manim_renderer.resolvers.anchor import parse_anchor
from manim_renderer.theme.palette import SEMANTIC, UI
from manim_renderer.theme.timing import TIMING
from manim_renderer.theme.typography import FONTS, FONT_SCALE


# Visual defaults
_BUBBLE_PADDING_X = 0.35
_BUBBLE_PADDING_Y = 0.20
_CORNER_RADIUS = 0.12
_BUBBLE_STROKE = 1.5
_LEADER_STROKE = 2.0


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

        # Build the bubble at origin.
        self._build_bubble()

        # Leader is added in position_finalized after we know absolute coords.
        # Initialize to None so anchor lookups can detect "no leader yet".
        self._leader_mob = None
        self._leader_endpoints: tuple[np.ndarray, np.ndarray] | None = None

    # --- bubble construction -------------------------------------------------

    def _build_bubble(self) -> None:
        from manim import Tex  # local import — avoid LaTeX dep at module load

        text_color = (
            UI.get(self._color_key)
            or SEMANTIC.get(self._color_key)
            or UI["text_primary"]
        )
        if self._color_key is not None and self._color_key not in {**UI, **SEMANTIC}:
            raise ValueError(
                f"CalloutBox color must be a UI or SEMANTIC palette key; "
                f"got {self._color_key!r}"
            )

        # Build the text first to size the bubble around it.
        self._text_mob = Text(
            self._text_str,
            font=FONTS["primary"],
            font_size=FONT_SCALE[self.format]["caption"],
            color=text_color,
        )

        # Wrap text if it exceeds max_width — Manim's Text doesn't auto-wrap,
        # so we split on spaces and rebuild as a multi-line Text. This is a
        # rough approach; CalloutBox is for short annotations, not paragraphs.
        if self._text_mob.width > self._max_width:
            self._text_mob = self._wrap_text()

        # Bubble: rounded rect padded around the text.
        bubble = RoundedRectangle(
            width=self._text_mob.width + 2 * _BUBBLE_PADDING_X,
            height=self._text_mob.height + 2 * _BUBBLE_PADDING_Y,
            corner_radius=_CORNER_RADIUS,
            color=UI["border"],
            fill_color=UI["surface"],
            fill_opacity=0.95,
            stroke_width=_BUBBLE_STROKE,
        )
        self._bubble_mob = bubble
        # Order: bubble first so text renders on top.
        self.add(self._bubble_mob, self._text_mob)
        self._text_mob.move_to(self._bubble_mob.get_center())

    def _wrap_text(self) -> Text:
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
        return Text(
            "\n".join(lines),
            font=FONTS["primary"],
            font_size=FONT_SCALE[self.format]["caption"],
            color=self._text_mob.color,
            line_spacing=0.85,
        )

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

    # --- bespoke entrance: bubble first, then leader -------------------------

    def entrance(self, effect: str, timing: str, **extra):
        run_time = TIMING[timing]
        # Bubble + text together (they're sibling submobjects we built first)
        bubble_text_group = VGroup(self._bubble_mob, self._text_mob)

        if effect == "fade-in":
            bubble_anim = FadeIn(bubble_text_group, run_time=run_time)
        elif effect in ("grow-up", "grow-down", "slide-left", "slide-right",
                         "slide-up", "slide-down", "write-in"):
            # Defer to the entrance effects subsystem applied to the bubble+text
            from manim_renderer.effects.entrances import get_entrance
            bubble_anim = get_entrance(effect, bubble_text_group, timing, **extra)
        else:
            return super().entrance(effect, timing, **extra)

        if self._leader_mob is None:
            return bubble_anim

        leader_anim = Create(self._leader_mob, run_time=TIMING["fast"])
        return Succession(bubble_anim, leader_anim)

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

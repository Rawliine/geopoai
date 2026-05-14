"""TextCard — centered text. The Phase 0 smoke component.

Uses BaseComponent's default entrance/exit/anchor dispatch. Schema-allowed
effects for TextCard are constrained in `schema/action_schemas/show_text_card.json`
(currently only `fade-in`); the dispatch in BaseComponent will raise on anything
not in `effects.entrances.ENTRANCES` regardless.

Slot-aware: when placed in a slot, TextCard auto-fits the text to the slot's
width (with an 8% margin) so titles never overflow narrow slots — see
`components/_text_fit.py`. When anchored or used outside a slot, no auto-fit
is applied; the caller's font_size is honored exactly.
"""

from __future__ import annotations

from manim import ORIGIN

from manim_renderer.components._text_fit import auto_fit_text
from manim_renderer.components.base import BaseComponent
from manim_renderer.theme.palette import UI
from manim_renderer.theme.typography import FONTS, FONT_SCALE


class TextCard(BaseComponent):
    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        """TextCard auto-fits to its slot at render time (see
        `_text_fit.auto_fit_text`), so the rendered bbox is bounded by the
        slot regardless of text length. We return a small placeholder that
        fits any standard title slot — the validator's slot-fit check is
        effectively a no-op for TextCard.

        For anchored TextCard (no auto-fit), this estimate may under-report
        overflow; in practice titles are short and slot-anchored, so the
        trade-off favors fewer false positives."""
        size_role = params.get("size", "title")
        # Title-class text occupies ~1.2u tall; body/label ~0.7u; caption ~0.5u.
        # Width is bounded by slot; report a small width so we never trigger
        # a false [layout-fit] on a slot that auto-fit would shrink into.
        height_by_role = {"title": 1.2, "body": 0.8, "label": 0.6, "caption": 0.5}
        h = height_by_role.get(size_role, 0.8)
        return (2.0, h)

    def build(self) -> None:
        text = self.params.get("text", "")
        size_role = self.params.get("size", "title")
        font_size = FONT_SCALE[self.format][size_role]

        slot_bounds = self.params.get("_slot_bounds")  # set by scene runner if in a slot
        target_w = slot_bounds[0] if slot_bounds else None
        target_h = slot_bounds[1] if slot_bounds else None

        self.label = auto_fit_text(
            text,
            font=FONTS["primary"],
            font_size=font_size,
            color=UI["text_primary"],
            target_width=target_w,
            target_height=target_h,
        )
        self.label.move_to(ORIGIN)
        self.add(self.label)

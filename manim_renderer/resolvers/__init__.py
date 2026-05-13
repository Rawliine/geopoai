"""Resolvers — pure functions that turn LLM-friendly tokens into Manim primitives.

Public API:
  * `resolve_anchor(anchor, id_to_mobject, format, ...)` — anchor string -> coord
  * `resolve_size(role, format, kind)` -> `(width, height)` in Manim units
  * `parse_anchor(anchor)` -> `(token, id)` (for validators)
  * `ANCHOR_TOKENS`, `SIZE_ROLES`, `SIZE_KINDS` — for schema enums

Camera resolver lives in Phase 2 — not present yet.
"""

from manim_renderer.resolvers.anchor import (
    ANCHOR_TOKENS,
    DEFAULT_ANCHOR_BUFF,
    parse_anchor,
    place_at_anchor,
    resolve_anchor,
)
from manim_renderer.resolvers.size import SIZE_KINDS, SIZE_ROLES, resolve_size

__all__ = [
    "ANCHOR_TOKENS",
    "DEFAULT_ANCHOR_BUFF",
    "SIZE_KINDS",
    "SIZE_ROLES",
    "parse_anchor",
    "place_at_anchor",
    "resolve_anchor",
    "resolve_size",
]

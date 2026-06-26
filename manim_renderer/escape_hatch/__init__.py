"""Guarded custom-Manim escape hatch — one-off scenes under strict lint."""

from manim_renderer.escape_hatch.contract import EscapeHatchSpec, parse_escape_hatch

__all__ = ["EscapeHatchSpec", "parse_escape_hatch"]

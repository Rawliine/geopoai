"""Easing palette. Resolves names to Manim rate_functions."""

from manim import rate_functions as rf

EASE = {
    "enter": rf.ease_out_cubic,
    "exit": rf.ease_in_cubic,
    "emphasis": rf.ease_in_out_cubic,
    "linear": rf.linear,
    "impact": rf.ease_out_back,
    "spring": rf.ease_out_elastic,
}

"""Unit tests for the slot-aware text auto-fit helper."""

from __future__ import annotations

import logging

import pytest

from manim_renderer.components._text_fit import auto_fit_text
from manim_renderer.theme.typography import FONTS

logging.getLogger("manim").setLevel(logging.ERROR)


def test_no_target_no_scaling():
    """target_width=None and target_height=None → text stays at requested size."""
    mob = auto_fit_text(
        "Prisoners Dilemma",
        font=FONTS["primary"],
        font_size=84,
        color="#ffffff",
        target_width=None,
    )
    # The "natural" width at 84pt — store as baseline for comparison tests.
    assert mob.width > 0


def test_fits_when_text_already_within_target():
    """Short text in a wide slot → not scaled."""
    natural = auto_fit_text("hi", font=FONTS["primary"], font_size=48,
                             color="#fff", target_width=None)
    fitted = auto_fit_text("hi", font=FONTS["primary"], font_size=48,
                            color="#fff", target_width=10.0)
    # Same text, wide slot → identical width
    assert abs(natural.width - fitted.width) < 1e-6


def test_scales_down_when_too_wide_and_target_reachable():
    """Moderately-too-wide text gets scaled to within target.

    Uses a target large enough that scaling can reach it without hitting the
    min_scale floor.
    """
    natural = auto_fit_text(
        "Wide but reachable",
        font=FONTS["primary"], font_size=84, color="#fff", target_width=None,
    )
    fitted = auto_fit_text(
        "Wide but reachable",
        font=FONTS["primary"], font_size=84, color="#fff",
        target_width=natural.width * 0.6,
    )
    # Confirm scaling happened
    assert fitted.width < natural.width
    # With the 0.92 margin and natural*0.6 target, fitted should sit at
    # roughly natural*0.6*0.92 ≈ natural*0.55
    assert 0.50 < fitted.width / natural.width < 0.60


def test_min_scale_floor_clamps_extreme_targets():
    """An impossibly narrow target hits the min_scale floor and stops shrinking."""
    natural = auto_fit_text(
        "Lorem ipsum dolor sit amet" * 5,
        font=FONTS["primary"], font_size=84, color="#fff", target_width=None,
    )
    fitted = auto_fit_text(
        "Lorem ipsum dolor sit amet" * 5,
        font=FONTS["primary"], font_size=84, color="#fff",
        target_width=0.5,  # impossibly narrow
        min_scale=0.4,
    )
    # fitted.width / natural.width should be exactly the min_scale.
    ratio = fitted.width / natural.width
    assert 0.39 < ratio < 0.41


def test_height_constraint_triggers_scaling():
    """target_height also triggers scaling when it would shrink more than width."""
    natural = auto_fit_text(
        "TallText",
        font=FONTS["primary"], font_size=120, color="#fff",
        target_width=None,
    )
    fitted = auto_fit_text(
        "TallText",
        font=FONTS["primary"], font_size=120, color="#fff",
        target_width=None,
        target_height=natural.height * 0.5,
    )
    # Confirm scaling happened (height shrunk meaningfully)
    assert fitted.height < natural.height * 0.6


def test_width_and_height_both_apply_smaller_scale_wins():
    """When both axes would scale, the smaller scale factor wins."""
    natural = auto_fit_text(
        "Wide and tall text",
        font=FONTS["primary"], font_size=84, color="#fff", target_width=None,
    )
    # Pick targets that demand DIFFERENT scales; the smaller one should win.
    # width target needs scale ~0.7; height target needs scale ~0.4.
    fitted = auto_fit_text(
        "Wide and tall text",
        font=FONTS["primary"], font_size=84, color="#fff",
        target_width=natural.width * 0.7,
        target_height=natural.height * 0.4,
    )
    # Both dimensions scale by the SAME (smaller) factor.
    width_ratio = fitted.width / natural.width
    height_ratio = fitted.height / natural.height
    assert abs(width_ratio - height_ratio) < 0.02
    # And the actual ratio is closer to 0.4 (height-driven) than 0.7
    assert width_ratio < 0.5

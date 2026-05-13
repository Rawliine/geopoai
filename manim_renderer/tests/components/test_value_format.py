"""Unit tests for value formatters. Pure functions — no rendering."""

from __future__ import annotations

import pytest

from manim_renderer.components.data_viz._value_format import (
    VALUE_FORMATS,
    format_value,
)


_MINUS = "−"  # U+2212


# --- int ---------------------------------------------------------------------

@pytest.mark.parametrize("v,expected", [
    (0, "0"),
    (42, "42"),
    (1234, "1,234"),
    (1_234_567, "1,234,567"),
    (-42, _MINUS + "42"),
    (-1234, _MINUS + "1,234"),
    (3.7, "4"),  # rounds
])
def test_int_format(v, expected):
    assert format_value(v, "int") == expected


# --- decimal -----------------------------------------------------------------

@pytest.mark.parametrize("v,decimals,expected", [
    (3.14159, 2, "3.14"),
    (3.14159, 4, "3.1416"),
    (-3.14, 1, _MINUS + "3.1"),
    (1234.5, 1, "1,234.5"),
])
def test_decimal_format(v, decimals, expected):
    assert format_value(v, "decimal", decimals=decimals) == expected


# --- pct ---------------------------------------------------------------------

def test_pct_appends_percent_sign():
    assert format_value(42.5, "pct") == "42.5%"
    assert format_value(-3.14, "pct", decimals=2) == _MINUS + "3.14%"


# --- k / m -------------------------------------------------------------------

def test_k_suffix():
    assert format_value(1500, "k") == "1.5K"
    assert format_value(12_000, "k") == "12.0K"


def test_m_suffix():
    assert format_value(1_500_000, "m") == "1.5M"
    assert format_value(7_300_000, "m", decimals=2) == "7.30M"


# --- currency ----------------------------------------------------------------

def test_currency_default_dollar():
    assert format_value(1234.5, "currency") == "$1,234.50"


def test_currency_explicit_suffix():
    assert format_value(1500, "currency", suffix="K") == "$1.50K"
    assert format_value(1_200_000, "currency", suffix="M") == "$1.20M"


def test_currency_auto_suffix():
    assert format_value(500, "currency", suffix="auto") == "$500.00"
    assert format_value(1500, "currency", suffix="auto") == "$1.50K"
    assert format_value(1_200_000, "currency", suffix="auto") == "$1.20M"
    assert format_value(2_500_000_000, "currency", suffix="auto") == "$2.50B"


def test_currency_alt_symbol():
    assert format_value(500, "currency", symbol="€") == "€500.00"


def test_currency_negative_uses_typographic_minus():
    assert format_value(-50, "currency") == _MINUS + "$50.00"


# --- signed ------------------------------------------------------------------

def test_signed_positive_prefixed_with_plus():
    assert format_value(15.3, "signed") == "+15.3"


def test_signed_negative_uses_typographic_minus():
    assert format_value(-3.4, "signed") == _MINUS + "3.4"


def test_signed_zero_is_zero():
    assert format_value(0, "signed") == "0.0"


# --- duration ----------------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0, "0s"),
    (45, "45s"),
    (90, "1m 30s"),
    (3600, "1h"),
    (7325, "2h 2m"),
    (86400, "1d"),
    (90061, "1d 1h"),
])
def test_duration_format(seconds, expected):
    assert format_value(seconds, "duration") == expected


def test_duration_negative():
    assert format_value(-45, "duration") == _MINUS + "45s"


# --- ratio -------------------------------------------------------------------

def test_ratio_list_form():
    assert format_value([3, 1], "ratio") == "3:1"
    assert format_value([10, 4], "ratio") == "5:2"  # gcd reduction
    assert format_value([7, 3], "ratio") == "7:3"


def test_ratio_scalar_implies_to_one():
    assert format_value(2.5, "ratio") == "2.5:1"


def test_ratio_bad_input_raises():
    with pytest.raises(TypeError):
        format_value({"a": 1}, "ratio")


# --- scientific --------------------------------------------------------------

def test_scientific_basic():
    assert format_value(1500000, "scientific") == "1.50×10⁶"
    assert format_value(0.0042, "scientific", decimals=2) == "4.20×10⁻³"


def test_scientific_zero():
    assert format_value(0, "scientific") == "0"


def test_scientific_negative():
    assert format_value(-1500, "scientific") == _MINUS + "1.50×10³"


# --- meta --------------------------------------------------------------------

def test_unknown_format_raises():
    with pytest.raises(KeyError, match="unknown value_format"):
        format_value(42, "elephant")


def test_value_formats_constant_complete():
    """VALUE_FORMATS must list exactly the keys in FORMATTERS (used by schema enum)."""
    expected = {"int", "decimal", "pct", "k", "m",
                "currency", "signed", "duration", "ratio", "scientific"}
    assert set(VALUE_FORMATS) == expected

"""Value formatters — shared across data_viz components.

The same `value_format` keys are accepted by StatBlock (full value), BarChart
(value labels above bars), and LineChart (axis tick labels). Adding a format
means appending a function here and adding the key to the corresponding schema
enum (`scene_schema.json#/definitions/value_format`).

Schema-allowed keys:
  int, decimal, pct, k, m, currency, signed, duration, ratio, scientific

Each formatter takes (value, **opts) -> str. Opts vary per format; defaults
make every formatter callable with just `value`.

Locale: en-US conventions only (comma thousands, dot decimal). Phase 1 doesn't
support i18n; deferred to a later phase if content demand emerges.
"""

from __future__ import annotations

import math
from typing import Any, Callable

# U+2212 MINUS SIGN — typographically correct for editorial display.
# Hyphen-minus (U+002D) is reserved for ranges/IDs.
_MINUS = "−"


# --- formatters --------------------------------------------------------------

def _fmt_int(value: float, **_) -> str:
    if value < 0:
        return _MINUS + f"{int(abs(round(value))):,}"
    return f"{int(round(value)):,}"


def _fmt_decimal(value: float, *, decimals: int = 1, **_) -> str:
    sign, mag = (_MINUS, abs(value)) if value < 0 else ("", value)
    return f"{sign}{mag:,.{decimals}f}"


def _fmt_pct(value: float, *, decimals: int = 1, **_) -> str:
    """Value is the percentage itself (e.g. 42.5 → '42.5%'), not a fraction."""
    return _fmt_decimal(value, decimals=decimals) + "%"


def _fmt_k(value: float, *, decimals: int = 1, **_) -> str:
    """Thousands suffix. 1500 → '1.5K', 12000 → '12.0K'."""
    return _fmt_decimal(value / 1_000, decimals=decimals) + "K"


def _fmt_m(value: float, *, decimals: int = 1, **_) -> str:
    """Millions suffix. 1_500_000 → '1.5M'."""
    return _fmt_decimal(value / 1_000_000, decimals=decimals) + "M"


_CURRENCY_DIVISORS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _fmt_currency(
    value: float,
    *,
    symbol: str = "$",
    decimals: int = 2,
    suffix: str | None = None,  # None | "K" | "M" | "B" | "auto"
    **_,
) -> str:
    """Currency display.

      _fmt_currency(1234.5)                    -> "$1,234.50"
      _fmt_currency(1500, suffix="K")          -> "$1.50K"
      _fmt_currency(1_200_000, suffix="auto")  -> "$1.20M"
      _fmt_currency(500, symbol="€")           -> "€500.00"
    """
    abs_v = abs(value)
    sign = _MINUS if value < 0 else ""

    if suffix == "auto":
        if abs_v >= 1_000_000_000:
            suffix = "B"
        elif abs_v >= 1_000_000:
            suffix = "M"
        elif abs_v >= 1_000:
            suffix = "K"
        else:
            suffix = None

    if suffix in _CURRENCY_DIVISORS:
        abs_v = abs_v / _CURRENCY_DIVISORS[suffix]
        body = f"{abs_v:,.{decimals}f}{suffix}"
    else:
        body = f"{abs_v:,.{decimals}f}"

    return f"{sign}{symbol}{body}"


def _fmt_signed(value: float, *, decimals: int = 1, **_) -> str:
    """Always shows leading + or − (typographic minus). Auto-color hint left to caller."""
    if value > 0:
        return "+" + _fmt_decimal(value, decimals=decimals)
    if value < 0:
        return _fmt_decimal(value, decimals=decimals)  # already gets minus from _fmt_decimal
    return _fmt_decimal(0, decimals=decimals)


def _fmt_duration(value: float, **_) -> str:
    """Seconds → `1d 2h`, `2h 15m`, `45s`, etc. Picks the two largest non-zero
    units. Skips zero units entirely (`3600` → `"1h"`, not `"1h 0m"`)."""
    if value < 0:
        return _MINUS + _fmt_duration(-value)
    secs = int(round(value))
    units = [
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ]
    parts: list[str] = []
    for label, size in units:
        n, secs = divmod(secs, size)
        if n:
            parts.append(f"{n}{label}")
            if len(parts) == 2:
                break
    if not parts:
        return "0s"
    return " ".join(parts)


def _fmt_ratio(value: Any, **_) -> str:
    """Accepts a [a, b] list (canonical) or a float (interpreted as a:1)."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        a, b = value
        # Reduce by gcd if both ints.
        if isinstance(a, int) and isinstance(b, int) and b != 0:
            g = math.gcd(abs(a), abs(b))
            a, b = a // g, b // g
        return f"{a}:{b}"
    if isinstance(value, (int, float)):
        return f"{_fmt_decimal(value)}:1"
    raise TypeError(f"ratio formatter needs [a, b] or number, got {type(value).__name__}")


def _fmt_scientific(value: float, *, decimals: int = 2, **_) -> str:
    """1500000 -> '1.50×10⁶'. Uses superscript digits for the exponent."""
    if value == 0:
        return "0"
    sign = _MINUS if value < 0 else ""
    abs_v = abs(value)
    exponent = int(math.floor(math.log10(abs_v)))
    mantissa = abs_v / (10 ** exponent)
    return f"{sign}{mantissa:.{decimals}f}×10{_superscript(exponent)}"


def _superscript(n: int) -> str:
    """Convert integer to Unicode superscript characters (digits + minus sign)."""
    table = {"-": "⁻", "0": "⁰", "1": "¹", "2": "²",
             "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
             "7": "⁷", "8": "⁸", "9": "⁹"}
    return "".join(table[c] for c in str(n))


# --- registry ----------------------------------------------------------------

FORMATTERS: dict[str, Callable[..., str]] = {
    "int":        _fmt_int,
    "decimal":    _fmt_decimal,
    "pct":        _fmt_pct,
    "k":          _fmt_k,
    "m":          _fmt_m,
    "currency":   _fmt_currency,
    "signed":     _fmt_signed,
    "duration":   _fmt_duration,
    "ratio":      _fmt_ratio,
    "scientific": _fmt_scientific,
}

VALUE_FORMATS: tuple[str, ...] = tuple(sorted(FORMATTERS))


def format_value(value: Any, value_format: str = "int", **opts) -> str:
    fn = FORMATTERS.get(value_format)
    if fn is None:
        raise KeyError(
            f"unknown value_format {value_format!r}; available: {VALUE_FORMATS}"
        )
    return fn(value, **opts)

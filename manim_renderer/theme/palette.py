"""Color palette. Must mirror renderer/effects.css (CI diff in Phase 2).

`pick_text_color(bg_hex)` is a utility for auto-contrast — given a background
hex, returns the better-contrasting palette text hex (`text_primary` for
dark backgrounds, `background` for light). Uses W3C relative luminance
(not WCAG contrast ratio — we only need a binary light/dark decision)."""

ACTORS = {
    "actor_a": "#3498db",
    "actor_b": "#e74c3c",
    "actor_c": "#2ecc71",
    "actor_d": "#f39c12",
    "actor_e": "#9b59b6",
}

SEMANTIC = {
    "positive": "#2ecc71",
    "negative": "#e74c3c",
    "neutral": "#95a5a6",
    "highlight": "#f1c40f",
    "contested": "#e67e22",
}

UI = {
    "background": "#0e1116",
    "surface": "#1a1f2e",
    "border": "#2c3e50",
    "text_primary": "#ecf0f1",
    "text_secondary": "#95a5a6",
    "text_accent": "#f1c40f",
}


def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected 6-digit hex, got {hex_str!r}")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def _relative_luminance(hex_str: str) -> float:
    """W3C relative luminance in [0, 1]."""
    r, g, b = _hex_to_rgb(hex_str)

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def pick_text_color(bg_hex: str) -> str:
    """Return the hex of the better-contrasting palette text color.

    Threshold 0.5 on relative luminance: below → light text (`text_primary`),
    above → dark text (`background`). Single decision boundary by design;
    callers needing finer contrast should compute WCAG ratios directly."""
    return UI["text_primary"] if _relative_luminance(bg_hex) < 0.5 else UI["background"]

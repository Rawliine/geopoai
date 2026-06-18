"""Icon — a provisioned SVG glyph or flag, brand-tinted with optional glow.

Loads an SVG by name from a provisioned icon pack under `assets/icons/<pack>/`
(see `tools/prepare_assets.py`). Two addressing forms:

  * ``icon: "shield"``   — bare name → the default ``lucide`` pack (outline icons,
                            stroke-tinted by `color`).
  * ``icon: "flag:ma"``  — ``flag:`` prefix → the ``circle-flags`` pack
                            (``ma.svg``); flags are multi-color and NOT tinted.

Params:
  * ``icon``  (required) — pack-qualified glyph name (see above).
  * ``color``  — palette role token used for the tint AND the glow hue. Role
                 tokens (highlight/threat/ally/contested/neutral) carry a matched
                 glow; other palette keys tint flat. Default ``neutral``. Ignored
                 for flags.
  * ``glow``   — bool; when true, render a soft halo behind the glyph using the
                 token glow radii/opacity (`tokens.glow`).
  * ``size``   — small | medium | large; the glyph height is FONT_SCALE-relative
                 (a multiple of the title type height for the format).

Sizes scale with the brand type scale rather than hardcoded units, so icons sit
consistently next to text.
"""

from __future__ import annotations

from pathlib import Path

from manim import ORIGIN, SVGMobject, VGroup

from manim_renderer.components.base import BaseComponent
from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI
from manim_renderer.theme.spacing import text_height_units

_ICONS_ROOT = Path(__file__).resolve().parents[3] / "assets" / "icons"

# Glyph height as a multiple of the format's title type height.
_SIZE_MULT = {"small": 1.0, "medium": 1.6, "large": 2.4}
_DEFAULT_SIZE = "medium"
_DEFAULT_COLOR = "neutral"
# `flag:` addresses the circle-flags pack; bare names use lucide.
_FLAG_PACK = "circle-flags"
_DEFAULT_PACK = "lucide"

# Token glow fallback (mirrors config/design_tokens.json:glow).
_GLOW_FALLBACK = {"core_px": 2, "halo_px": 6, "halo_opacity": 0.35}


def _resolve_icon_path(icon: str) -> tuple[Path, str]:
    """Map an ``icon`` string to (svg_path, pack_slug). Searches the pack dir
    recursively so packs that nest under a subdir (lucide → ``icons/``) work."""
    if ":" in icon:
        prefix, name = icon.split(":", 1)
        pack = _FLAG_PACK if prefix == "flag" else prefix
    else:
        pack, name = _DEFAULT_PACK, icon
    pack_dir = _ICONS_ROOT / pack
    matches = sorted(pack_dir.rglob(f"{name}.svg"))
    if not matches:
        raise ValueError(
            f"icon {icon!r}: no {name!r}.svg in provisioned pack {pack!r} "
            f"({pack_dir}). Provision it via tools/prepare_assets.py --add {pack}."
        )
    return matches[0], pack


def _role_colors(color: str) -> tuple[str, str]:
    """Resolve a palette key to ``(tint_hex, glow_hex)``. Role tokens
    (tokens.palette.roles) carry a matched glow; other palette keys glow in
    their own hue."""
    try:
        from tools.tokens import load_tokens

        roles = load_tokens()["palette"]["roles"]
        if color in roles:
            return roles[color]["core"], roles[color].get("glow", roles[color]["core"])
    except Exception:
        pass
    palette = {**ACTORS, **SEMANTIC, **UI}
    if color in palette:
        return palette[color], palette[color]
    raise ValueError(
        f"icon color {color!r} is not a palette role or key; "
        f"available roles: highlight/threat/ally/contested/neutral, "
        f"or palette keys {sorted(palette)}"
    )


def _glow_tokens() -> dict:
    try:
        from tools.tokens import load_tokens

        return {**_GLOW_FALLBACK, **(load_tokens().get("glow") or {})}
    except Exception:
        return dict(_GLOW_FALLBACK)


class Icon(BaseComponent):
    """Provisioned SVG icon / flag with brand tint + optional glow."""

    @classmethod
    def measure(cls, params: dict, format: str) -> tuple[float, float]:
        # Icons render ~square; report the glyph box plus a little glow padding so
        # the dry-run leaves room. Width is approximated as height (square-ish).
        h = text_height_units("title", format) * _SIZE_MULT.get(
            params.get("size", _DEFAULT_SIZE), _SIZE_MULT[_DEFAULT_SIZE]
        )
        pad = 1.25 if params.get("glow") else 1.05
        return (h * pad, h * pad)

    def build(self) -> None:
        p = self.params
        icon = p.get("icon")
        if not icon:
            raise ValueError("Icon requires params.icon (e.g. 'shield' or 'flag:ma')")

        svg_path, pack = _resolve_icon_path(icon)
        glyph = SVGMobject(str(svg_path))

        target_h = text_height_units("title", self.format) * _SIZE_MULT.get(
            p.get("size", _DEFAULT_SIZE), _SIZE_MULT[_DEFAULT_SIZE]
        )
        glyph.scale_to_fit_height(target_h)

        is_flag = pack == _FLAG_PACK
        tint_hex, glow_hex = _role_colors(p.get("color", _DEFAULT_COLOR))
        # Flags are intentionally multi-color; only single-color glyphs tint.
        if not is_flag:
            glyph.set_color(tint_hex)

        if p.get("glow"):
            self.add(self._build_glow(glyph, glow_hex))
        self.add(glyph)
        self._glyph = glyph
        self.move_to(ORIGIN)

    @staticmethod
    def _build_glow(glyph: SVGMobject, glow_hex: str) -> VGroup:
        """Soft halo from token glow radii: two stroked copies behind the glyph,
        widening + fading outward (mirrors the neon callout glow pattern)."""
        g = _glow_tokens()
        halo = float(g["halo_px"])
        op = float(g["halo_opacity"])
        layers = VGroup()
        for width, opacity in ((halo * 1.6, op * 0.5), (halo, op)):
            layer = glyph.copy()
            layer.set_stroke(color=glow_hex, width=width, opacity=opacity)
            layer.set_fill(opacity=0.0)
            layers.add(layer)
        return layers

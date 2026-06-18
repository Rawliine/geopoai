"""Register provisioned brand fonts with Pango for Manim renders."""

from __future__ import annotations

import logging
from pathlib import Path

from assets.catalog import pack_slug

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FONTS_ROOT = _REPO_ROOT / "assets" / "font"
_REGISTERED: set[str] = set()
_DONE = False

logger = logging.getLogger(__name__)


def _token_font_families() -> tuple[str, ...]:
    try:
        from tools.tokens import load_tokens

        typo = load_tokens()["typography"]
        return (
            typo["primary"],
            typo["display"],
            typo["mono"],
            typo["math"],
        )
    except Exception:
        from manim_renderer.theme.typography import FONTS

        return tuple(FONTS[k] for k in ("primary", "display", "mono", "math"))


def ensure_brand_fonts_registered() -> None:
    """Load brand TTFs from ``assets/font/<pack-slug>/`` into Pango so renders
    are font-correct on any machine without system installs (idempotent).

    We register globally via ``manimpango.register_font`` rather than Manim's
    ``manim.utils.register_font`` context manager: the latter de-registers the
    font when its ``with`` block exits, which would drop the family before the
    scene's many ``Text`` mobjects are rasterized. A render is long-lived and
    every component expects the brand families to stay resident, so a one-shot
    global registration (the call the context manager wraps) is the right tool.
    """
    global _DONE
    if _DONE:
        return

    import manimpango

    for family in _token_font_families():
        font_dir = _FONTS_ROOT / pack_slug(family)
        if not font_dir.is_dir():
            logger.warning(
                "brand font %r not provisioned — run: "
                "python tools/prepare_assets.py --add %r",
                family,
                family,
            )
            continue
        for ttf in sorted(font_dir.rglob("*.ttf")):
            path = str(ttf.resolve())
            if path in _REGISTERED:
                continue
            if not manimpango.register_font(path):
                logger.warning("failed to register font file %s", path)
                continue
            _REGISTERED.add(path)
            logger.debug("registered font file %s", path)

    _DONE = True

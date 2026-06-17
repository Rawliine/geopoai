"""Composition layer — episode assembly stubs (W17 implements)."""

from composition.captions import build as build_captions
from composition.engine import compose
from composition.export import profiles
from composition.sound import build as build_sound

__all__ = [
    "build_captions",
    "build_sound",
    "compose",
    "profiles",
]

"""Layout primitives. A Layout is a set of named slots; each slot is a Rect
in Manim unit space (origin at frame center, y-up)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass(frozen=True)
class Rect:
    cx: float
    cy: float
    width: float
    height: float

    @property
    def center(self) -> np.ndarray:
        return np.array([self.cx, self.cy, 0.0])

    @property
    def size(self) -> tuple[float, float]:
        return (self.width, self.height)


@dataclass(frozen=True)
class Layout:
    name: str
    format: str  # "horizontal" | "vertical"
    slots: Dict[str, Rect]

    def slot(self, name: str) -> Rect:
        if name not in self.slots:
            raise KeyError(
                f"layout {self.name!r} ({self.format}) has no slot {name!r}; "
                f"available: {sorted(self.slots)}"
            )
        return self.slots[name]

    def has_slot(self, name: str) -> bool:
        return name in self.slots

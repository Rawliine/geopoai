"""EffectSpec — structured descriptor for an effect factory.

Effects are pure factories: they take a mobject + run_time + per-effect params and
return a Manim Animation. EffectSpec captures three things per effect:

  * `factory`  — the callable
  * `required` — params (besides run_time) the caller must supply or dispatch errors
  * `optional` — params with defaults; merged into the call

This shape lets us:
  * give the LLM precise errors when a required param is missing
  * generate JSON-schema fragments for per-effect params (Phase 2 escalation)
  * autogenerate the `_skill.md` effect catalog without re-deriving from source
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class EffectSpec:
    name: str
    factory: Callable[..., Any]
    required: tuple[str, ...] = ()
    optional: dict[str, Any] = field(default_factory=dict)

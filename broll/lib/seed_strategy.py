"""broll.lib.seed_strategy — deterministic seeds for AI generation.

Same ``(prompt, model, lora_stack)`` ⇒ same seed ⇒ same clip ⇒ never
regenerated. This is one half of the "cache aggressively" policy in
``plan(1).md`` Phase 2; the other half (file-level cache by recipe hash)
lives in :mod:`broll.sources._ai_base`.

ComfyUI's ``KSampler`` seed slot is a 64-bit-ish unsigned integer; in
practice it's safe to use any non-negative int that fits in 64 bits. We
deliberately stay in 32-bit-unsigned range so the seed renders cleanly in
logs and in URLs.

Override
--------
``shot_spec["_seed"]`` always wins. Set this when you specifically want a
different roll of the dice without changing the prompt.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


_SEED_MAX = (1 << 32) - 1  # unsigned 32-bit


def _normalize_lora_stack(lora_stack: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Sort LoRA entries so order doesn't shift the hash."""
    if not lora_stack:
        return []
    return sorted(
        ({"name": str(l.get("name", "")), "strength": float(l.get("strength", 0))} for l in lora_stack),
        key=lambda l: (l["name"], l["strength"]),
    )


def seed_for(
    prompt: str,
    model: str,
    *,
    salt: str | int | None = None,
    lora_stack: Iterable[dict[str, Any]] | None = None,
) -> int:
    """Return a deterministic seed in ``[0, 2^32 - 1]``.

    The hash inputs are the prompt, the model id, the optionally-provided
    salt, and the (sorted) LoRA stack. Two runs with identical inputs get
    identical seeds; changing any input changes the seed.
    """
    payload = json.dumps(
        {
            "prompt": prompt,
            "model": model,
            "salt": salt,
            "lora_stack": _normalize_lora_stack(lora_stack),
        },
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], byteorder="big") & _SEED_MAX


def seed_from_spec(
    shot_spec: dict[str, Any],
    *,
    model: str,
    prompt: str,
    lora_stack: Iterable[dict[str, Any]] | None = None,
) -> int:
    """Honour an explicit ``shot_spec["_seed"]`` override; else derive."""
    explicit = shot_spec.get("_seed")
    if explicit is not None:
        try:
            return int(explicit) & _SEED_MAX
        except (TypeError, ValueError):
            pass
    return seed_for(prompt, model, salt=shot_spec.get("_seed_salt"), lora_stack=lora_stack)

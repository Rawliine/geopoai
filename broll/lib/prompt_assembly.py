"""broll.lib.prompt_assembly — turn shot specs into ComfyUI-ready prompts.

Public surface:

    build_prompt(spec, *, model) -> AssembledPrompt
    load_lora_stack(model)       -> list[dict]

The assembler reads two files at import time:
    broll/prompts/style_tokens.md   — fenced blocks of positive/negative/tone tokens
    broll/prompts/lora_stack.json   — default LoRA stack per model

Both files are documented for human editing (see ai_prompt_template.md). The
parser is intentionally tolerant — missing blocks, unknown tones, malformed
JSON all degrade gracefully so a bad prompt file can't break the pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("broll.prompt_assembly")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_STYLE_TOKENS_PATH = _PROMPTS_DIR / "style_tokens.md"
_LORA_STACK_PATH = _PROMPTS_DIR / "lora_stack.json"

# Soft per-model word caps for the channel-style block. The user's intent is
# never truncated.
_MODEL_BUDGETS = {
    "ltx-2.3": 60,
    "wan-2.2": 120,
}
_DEFAULT_BUDGET = 80


@dataclass(slots=True)
class AssembledPrompt:
    """Result of :func:`build_prompt`."""

    positive: str
    negative: str
    lora_stack: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        """Render to the ``ai_metadata`` shape for asset_meta."""
        return {
            "prompt": self.positive,
            "negative_prompt": self.negative or None,
            "lora_stack": list(self.lora_stack),
        }


# ── Style tokens loader ──────────────────────────────────────────────────────
_FENCE_RE = re.compile(
    r"^```(?P<tag>[A-Za-z0-9:_-]+)\s*\n(?P<body>.*?)^```",
    re.DOTALL | re.MULTILINE,
)


def _load_style_blocks() -> dict[str, str]:
    """Parse the fenced blocks of style_tokens.md into a flat dict.

    Block tags follow the convention ``positive``, ``negative``, ``tone:<name>``.
    """
    if not _STYLE_TOKENS_PATH.exists():
        log.warning("style_tokens.md not found at %s; using empty defaults", _STYLE_TOKENS_PATH)
        return {}
    raw = _STYLE_TOKENS_PATH.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in _FENCE_RE.finditer(raw):
        tag = m.group("tag").strip().lower()
        body = m.group("body").strip()
        if tag and body:
            out[tag] = _normalize_text(body)
    return out


_STYLE_BLOCKS_CACHE: dict[str, str] | None = None


def _style_blocks() -> dict[str, str]:
    global _STYLE_BLOCKS_CACHE
    if _STYLE_BLOCKS_CACHE is None:
        _STYLE_BLOCKS_CACHE = _load_style_blocks()
    return _STYLE_BLOCKS_CACHE


def reload_style_blocks() -> None:
    """Drop the cache (used by tests when monkeypatching the file)."""
    global _STYLE_BLOCKS_CACHE
    _STYLE_BLOCKS_CACHE = None


# ── LoRA stack loader ────────────────────────────────────────────────────────
_LORA_STACK_CACHE: dict[str, Any] | None = None


def _lora_doc() -> dict[str, Any]:
    global _LORA_STACK_CACHE
    if _LORA_STACK_CACHE is not None:
        return _LORA_STACK_CACHE
    if not _LORA_STACK_PATH.exists():
        log.warning("lora_stack.json missing at %s; using empty default", _LORA_STACK_PATH)
        _LORA_STACK_CACHE = {"default": [], "by_model": {}}
        return _LORA_STACK_CACHE
    try:
        _LORA_STACK_CACHE = json.loads(_LORA_STACK_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.warning("lora_stack.json malformed (%s); using empty default", exc)
        _LORA_STACK_CACHE = {"default": [], "by_model": {}}
    return _LORA_STACK_CACHE


def reload_lora_stack() -> None:
    global _LORA_STACK_CACHE
    _LORA_STACK_CACHE = None


def load_lora_stack(model: str) -> list[dict[str, Any]]:
    """Return the LoRA list for ``model`` (or the default if unspecified)."""
    doc = _lora_doc()
    by_model = doc.get("by_model") or {}
    if model in by_model and isinstance(by_model[model], list):
        return [dict(l) for l in by_model[model]]
    default = doc.get("default") or []
    return [dict(l) for l in default if isinstance(l, dict)]


# ── Text helpers ─────────────────────────────────────────────────────────────
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?\s]+$")
_DEDUP_PUNCT_RE = re.compile(r"([.,;:!?])\1+")


def _normalize_text(s: str) -> str:
    s = _WHITESPACE_RE.sub(" ", s).strip()
    s = _DEDUP_PUNCT_RE.sub(r"\1", s)
    return s


def _join_phrases(parts: list[str]) -> str:
    cleaned = []
    for p in parts:
        if not p:
            continue
        p = _TRAILING_PUNCT_RE.sub("", _normalize_text(p))
        if p:
            cleaned.append(p)
    return ". ".join(cleaned) + ("." if cleaned else "")


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


# ── Public API ───────────────────────────────────────────────────────────────
def build_prompt(
    spec: dict[str, Any],
    *,
    model: str,
) -> AssembledPrompt:
    """Assemble positive + negative prompts and the LoRA stack for ``spec``.

    Parameters
    ----------
    spec:
        Shot spec dict (already schema-validated by the caller).
    model:
        Model id like ``"ltx-2.3"`` / ``"wan-2.2"``. Drives per-model word
        budgets and LoRA selection.

    Behaviour
    ---------
    * The user's ``intent`` is used verbatim and is NEVER truncated.
    * The channel-style block is truncated to a per-model word budget.
    * Tone block is appended only when ``spec.tone`` matches a known block
      (case-insensitive; just the first word of the tone is used so
      ``"calm, observational"`` matches ``tone:calm``).
    * ``spec.negative_intent`` (if any) is appended verbatim to the channel
      negatives.
    * ``spec._lora_stack`` overrides the default LoRA stack for this shot.
    """
    blocks = _style_blocks()
    intent = str(spec.get("intent") or "").strip()
    if not intent:
        raise ValueError("build_prompt requires a non-empty shot_spec.intent")

    budget = _MODEL_BUDGETS.get(model, _DEFAULT_BUDGET)

    style_positive = _truncate_words(blocks.get("positive", ""), budget)
    style_negative = blocks.get("negative", "")

    tone_raw = (spec.get("tone") or "").strip().lower()
    tone_block = ""
    if tone_raw:
        first = re.split(r"[\s,;]+", tone_raw, maxsplit=1)[0]
        tone_block = blocks.get(f"tone:{first}", "")

    positive = _join_phrases([intent, tone_block, style_positive])

    user_negative = str(spec.get("negative_intent") or "").strip()
    negative = _join_phrases([style_negative, user_negative])

    explicit_loras = spec.get("_lora_stack")
    if isinstance(explicit_loras, list):
        lora_stack = [dict(l) for l in explicit_loras if isinstance(l, dict)]
    else:
        lora_stack = load_lora_stack(model)

    return AssembledPrompt(positive=positive, negative=negative, lora_stack=lora_stack)

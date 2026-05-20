"""Prompt assembly: intent verbatim, tone application, model word budgets."""

from __future__ import annotations

import pytest

from broll.lib import prompt_assembly


@pytest.fixture(autouse=True)
def _reload_caches() -> None:
    prompt_assembly.reload_style_blocks()
    prompt_assembly.reload_lora_stack()


def test_intent_appears_verbatim() -> None:
    intent = "aerial of container ships at the Suez Canal at dawn"
    p = prompt_assembly.build_prompt({"intent": intent}, model="ltx-2.3")
    assert p.positive.startswith(intent)


def test_tone_block_applied_when_matched() -> None:
    p = prompt_assembly.build_prompt({"intent": "x city", "tone": "calm, observational"}, model="ltx-2.3")
    assert "unhurried camera" in p.positive  # from tone:calm block


def test_unknown_tone_silently_ignored() -> None:
    p = prompt_assembly.build_prompt({"intent": "x", "tone": "fluorescent"}, model="ltx-2.3")
    # Builds without raising; tone block simply absent.
    assert p.positive


def test_user_negative_appended() -> None:
    p = prompt_assembly.build_prompt(
        {"intent": "x", "negative_intent": "no people, no cars"},
        model="ltx-2.3",
    )
    assert "no people, no cars" in p.negative
    # Channel negatives also present.
    assert "watermark" in p.negative


def test_wan_budget_larger_than_ltx() -> None:
    intent = "x"  # short, so channel positives drive the length
    ltx = prompt_assembly.build_prompt({"intent": intent}, model="ltx-2.3")
    wan = prompt_assembly.build_prompt({"intent": intent}, model="wan-2.2")
    assert len(wan.positive.split()) >= len(ltx.positive.split())


def test_lora_stack_explicit_override() -> None:
    p = prompt_assembly.build_prompt(
        {"intent": "x", "_lora_stack": [{"name": "custom", "strength": 0.8}]},
        model="ltx-2.3",
    )
    assert p.lora_stack == [{"name": "custom", "strength": 0.8}]


def test_lora_stack_default_for_model() -> None:
    p = prompt_assembly.build_prompt({"intent": "x"}, model="ltx-2.3")
    assert any(l.get("name") == "Soft_Enhance_Style_LoRa" for l in p.lora_stack)


def test_to_metadata_shape() -> None:
    p = prompt_assembly.build_prompt(
        {"intent": "x", "negative_intent": "y"}, model="ltx-2.3",
    )
    md = p.to_metadata()
    assert "prompt" in md and md["prompt"]
    assert md["negative_prompt"]  # not None
    assert isinstance(md["lora_stack"], list)


def test_empty_intent_rejected() -> None:
    with pytest.raises(ValueError):
        prompt_assembly.build_prompt({"intent": "   "}, model="ltx-2.3")

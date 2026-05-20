"""Seed strategy determinism + override."""

from __future__ import annotations

from broll.lib import seed_strategy


def test_seed_is_deterministic() -> None:
    a = seed_strategy.seed_for("aerial city", "ltx-2.3")
    b = seed_strategy.seed_for("aerial city", "ltx-2.3")
    assert a == b
    assert 0 <= a < (1 << 32)


def test_seed_changes_with_prompt() -> None:
    a = seed_strategy.seed_for("aerial city", "ltx-2.3")
    b = seed_strategy.seed_for("aerial city different", "ltx-2.3")
    assert a != b


def test_seed_changes_with_model() -> None:
    a = seed_strategy.seed_for("aerial city", "ltx-2.3")
    b = seed_strategy.seed_for("aerial city", "wan-2.2")
    assert a != b


def test_seed_changes_with_lora_stack() -> None:
    a = seed_strategy.seed_for("aerial city", "ltx-2.3", lora_stack=[])
    b = seed_strategy.seed_for("aerial city", "ltx-2.3", lora_stack=[{"name": "x", "strength": 0.4}])
    assert a != b


def test_seed_stable_under_lora_reorder() -> None:
    stack_a = [{"name": "a", "strength": 0.3}, {"name": "b", "strength": 0.5}]
    stack_b = [{"name": "b", "strength": 0.5}, {"name": "a", "strength": 0.3}]
    assert (
        seed_strategy.seed_for("x", "ltx-2.3", lora_stack=stack_a)
        == seed_strategy.seed_for("x", "ltx-2.3", lora_stack=stack_b)
    )


def test_seed_changes_with_salt() -> None:
    a = seed_strategy.seed_for("x", "ltx-2.3", salt=1)
    b = seed_strategy.seed_for("x", "ltx-2.3", salt=2)
    assert a != b


def test_explicit_seed_override() -> None:
    spec = {"_seed": 42}
    assert seed_strategy.seed_from_spec(spec, model="ltx-2.3", prompt="x") == 42


def test_explicit_seed_bad_value_falls_through() -> None:
    spec = {"_seed": "not an int"}
    derived = seed_strategy.seed_from_spec(spec, model="ltx-2.3", prompt="x")
    assert isinstance(derived, int) and 0 <= derived < (1 << 32)

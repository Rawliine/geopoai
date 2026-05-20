"""Decision matrix behaviour."""

from __future__ import annotations

import pytest

from broll.lib.decision import DECISION_TABLE, VALID_STRATEGIES, decide
from broll.lib.errors import BrollError


def _spec(kind: str, **overrides) -> dict:
    base = {
        "shot_id": "t001",
        "intent": "x",
        "kind": kind,
        "duration_seconds": 4,
    }
    base.update(overrides)
    return base


def test_table_covers_every_kind_with_valid_strategies() -> None:
    for kind, row in DECISION_TABLE.items():
        assert row["strategy"] in VALID_STRATEGIES, f"{kind} has bad strategy"
        assert isinstance(row["ai_allowed"], bool)
        assert isinstance(row["hint_can_override"], bool)


@pytest.mark.parametrize(
    "kind,expected_strategy,expected_ai_allowed",
    [
        ("real_named_event",    "stock_only",  False),
        ("real_named_person",   "stock_only",  False),
        ("recognizable_place",  "stock_only",  False),
        ("archival_pre_2010",   "stock_only",  False),
        ("establishing",        "stock_first", True),
        ("conceptual",          "ai_only",     True),
        ("stylized_continuity", "ai_only",     True),
        ("filler",              "ai_first",    True),
    ],
)
def test_default_strategy_per_kind(kind, expected_strategy, expected_ai_allowed) -> None:
    d = decide(_spec(kind))
    assert d["strategy"] == expected_strategy
    assert d["ai_allowed"] is expected_ai_allowed


def test_hint_ignored_for_stock_only_kind() -> None:
    d = decide(_spec("real_named_event", stock_first=False))
    assert d["strategy"] == "stock_only"
    assert "fixed" in d["reason"]


def test_hint_ignored_for_ai_only_kind() -> None:
    d = decide(_spec("conceptual", stock_first=True))
    assert d["strategy"] == "ai_only"


def test_hint_flips_filler_to_stock_first() -> None:
    d = decide(_spec("filler", stock_first=True))
    assert d["strategy"] == "stock_first"


def test_hint_flips_establishing_to_ai_first() -> None:
    d = decide(_spec("establishing", stock_first=False))
    assert d["strategy"] == "ai_first"


def test_unknown_kind_raises() -> None:
    with pytest.raises(BrollError):
        decide({"kind": "unknown_kind"})

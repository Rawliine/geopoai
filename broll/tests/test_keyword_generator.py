"""Heuristic keyword generator."""

from __future__ import annotations

from broll.lib.keyword_generator import generate_queries


def test_empty_intent_returns_empty() -> None:
    assert generate_queries("") == []


def test_existing_queries_preserved_first() -> None:
    out = generate_queries(
        "aerial container ships at dawn",
        n=5,
        existing=["custom orchestrator query"],
    )
    assert out[0] == "custom orchestrator query"
    assert len(out) <= 5
    assert len(out) > 1  # heuristic should fill the rest


def test_n_zero_returns_empty() -> None:
    assert generate_queries("anything", n=0) == []


def test_results_are_unique() -> None:
    out = generate_queries("aerial container ships at sea at dawn drone", n=6)
    assert len(out) == len(set(q.lower() for q in out))


def test_heuristic_drops_stopwords() -> None:
    out = generate_queries("the cargo ships in the sea", n=3)
    assert all("the" not in q.split() for q in out)


def test_perspective_keyword_picked_up() -> None:
    out = generate_queries("aerial cargo ships at sea", n=5)
    assert any("aerial" in q for q in out)


class _BoomClient:
    def expand_queries(self, intent: str, *, n: int) -> list[str]:
        raise RuntimeError("LLM unavailable")


def test_llm_failure_falls_back_to_heuristic() -> None:
    out = generate_queries(
        "aerial container ships at dawn", n=3, llm_client=_BoomClient()
    )
    assert out, "fallback heuristic should still produce queries"

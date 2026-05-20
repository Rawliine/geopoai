"""broll.lib.decision — stock-first vs AI-first routing.

The decision matrix is data, not code branches. Update ``DECISION_TABLE`` here
when the policy changes; don't sprinkle ``if kind == ...`` elsewhere.

Strategy values
---------------
``stock_only``
    Stock cascade only. AI generation is forbidden even if the cascade returns
    nothing — surface the failure instead. Used for shots where AI substitution
    would damage credibility (real events, real people, recognizable places,
    pre-2010 archival).

``stock_first``
    Walk the stock cascade first; fall back to AI if the cascade returns no
    candidates or verification rejects all of them.

``ai_first``
    Try AI first; fall back to stock if AI verification keeps failing.

``ai_only``
    AI generation only. Stock is irrelevant (conceptual, stylized continuity).

The orchestrator can hint via ``stock_first: bool`` on the shot spec; that hint
is honoured only for kinds whose default is itself flexible. Kinds marked
``stock_only`` or ``ai_only`` ignore the hint.
"""

from __future__ import annotations

from typing import Any

from .errors import BrollError

# Centralised matrix. Keep keys aligned with the shot_spec_schema "kind" enum.
DECISION_TABLE: dict[str, dict[str, Any]] = {
    "real_named_event":     {"strategy": "stock_only",  "ai_allowed": False, "hint_can_override": False},
    "real_named_person":    {"strategy": "stock_only",  "ai_allowed": False, "hint_can_override": False},
    "recognizable_place":   {"strategy": "stock_only",  "ai_allowed": False, "hint_can_override": False},
    "archival_pre_2010":    {"strategy": "stock_only",  "ai_allowed": False, "hint_can_override": False},
    "establishing":         {"strategy": "stock_first", "ai_allowed": True,  "hint_can_override": True},
    "conceptual":           {"strategy": "ai_only",     "ai_allowed": True,  "hint_can_override": False},
    "stylized_continuity":  {"strategy": "ai_only",     "ai_allowed": True,  "hint_can_override": False},
    "filler":               {"strategy": "ai_first",    "ai_allowed": True,  "hint_can_override": True},
}

VALID_STRATEGIES = {"stock_only", "stock_first", "ai_first", "ai_only"}


def decide(shot_spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve a shot_spec into a routing decision.

    Returns a dict with:
        strategy:    final strategy (see VALID_STRATEGIES)
        ai_allowed:  bool — whether AI fallback is permitted at all
        reason:      short human-readable trace of how the decision was made
        kind:        echoed from the spec for downstream convenience

    Raises BrollError if ``kind`` is unknown.
    """
    kind = shot_spec.get("kind")
    if kind not in DECISION_TABLE:
        raise BrollError(
            f"unknown shot kind {kind!r}; valid kinds: {sorted(DECISION_TABLE)}"
        )

    row = DECISION_TABLE[kind]
    strategy = row["strategy"]
    ai_allowed = row["ai_allowed"]
    reason_parts = [f"kind={kind} → default={strategy}"]

    hint = shot_spec.get("stock_first")
    if hint is not None:
        if row["hint_can_override"]:
            # Honour orchestrator hint only when it doesn't contradict policy.
            if hint and strategy == "ai_first":
                strategy = "stock_first"
                reason_parts.append("hint stock_first=True → stock_first")
            elif (not hint) and strategy == "stock_first" and ai_allowed:
                strategy = "ai_first"
                reason_parts.append("hint stock_first=False → ai_first")
            else:
                reason_parts.append(f"hint stock_first={hint} ignored (no-op)")
        else:
            reason_parts.append(
                f"hint stock_first={hint} ignored (policy for kind={kind} is fixed)"
            )

    return {
        "strategy": strategy,
        "ai_allowed": ai_allowed,
        "kind": kind,
        "reason": "; ".join(reason_parts),
    }

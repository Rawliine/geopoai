"""AI router decisions."""

from __future__ import annotations

import pytest

from broll.lib import ai_router
from broll.lib.errors import BrollError


def _spec(intent: str, **overrides) -> dict:
    base = {"shot_id": "t", "intent": intent, "kind": "conceptual", "duration_seconds": 4}
    base.update(overrides)
    return base


def test_default_is_ltx() -> None:
    assert ai_router.pick_model(_spec("aerial of a city at dawn")) == ai_router.MODEL_LTX


def test_face_hint_routes_to_wan() -> None:
    assert ai_router.pick_model(_spec("close-up portrait of a speaker")) == ai_router.MODEL_WAN
    assert ai_router.pick_model(_spec("talking head against a plain wall")) == ai_router.MODEL_WAN


def test_face_in_aerial_stays_ltx() -> None:
    # Aerial framing reads small faces — LTX is fine.
    assert ai_router.pick_model(_spec("aerial of a crowd of faces in a square")) == ai_router.MODEL_LTX


def test_word_boundary_avoids_false_positive() -> None:
    # "surface" must not trigger on "face".
    assert ai_router.pick_model(_spec("water surface ripples at dusk")) == ai_router.MODEL_LTX


def test_explicit_override_wins() -> None:
    assert ai_router.pick_model(_spec("aerial city", _ai_model="wan-2.2")) == ai_router.MODEL_WAN
    assert ai_router.pick_model(_spec("close-up portrait", _ai_model="ltx-2.3")) == ai_router.MODEL_LTX


def test_unknown_override_raises() -> None:
    with pytest.raises(BrollError):
        ai_router.pick_model(_spec("anything", _ai_model="sora-99"))


def test_flux_ltx_pipeline_routes_to_flux_ltx_model() -> None:
    assert ai_router.pick_ai_model(
        _spec("chapter card mood", _pipeline="flux_ltx_i2v")
    ) == ai_router.MODEL_FLUX_LTX

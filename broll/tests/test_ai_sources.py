"""AI source end-to-end: prompt → ComfyUI mock → asset_wrapper.finalize."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from broll.lib import comfyui_client
from broll.sources import ltx_video, wan_video
from broll.sources._ai_base import AIGenerationError

from . import _comfyui_mock as mock


@pytest.fixture
def comfy_url():
    server, thread, url = mock.start()
    try:
        yield url
    finally:
        mock.stop(server, thread)


@pytest.fixture(autouse=True)
def _isolate_ai_cache(tmp_path, monkeypatch) -> None:
    """Redirect the AI recipe cache to a per-test tmp dir."""
    from broll.sources import _ai_base
    monkeypatch.setattr(_ai_base, "_AI_CACHE_DIR", tmp_path / "ai_cache")


def _spec(intent: str, **overrides) -> dict:
    base = {
        "shot_id": "test-ai-001",
        "intent": intent,
        "kind": "conceptual",
        "duration_seconds": 3.0,
        "format": "horizontal",
    }
    base.update(overrides)
    return base


def test_ltx_generate_writes_asset_and_meta(comfy_url, tmp_path) -> None:
    client = comfyui_client.ComfyUIClient(comfy_url, poll_interval=0.05)
    target = tmp_path / "out.mp4"
    meta = ltx_video.generate(_spec("aerial of a coastal city at dawn"), target, client=client)
    assert target.exists()
    assert (tmp_path / "out.mp4.meta.json").exists()
    assert meta["kind"] == "ai_video"
    assert meta["source"]["name"] == "ltx-2.3"
    assert meta["ai_metadata"]["model"] == "ltx-2.3"
    assert meta["ai_metadata"]["seed"] is not None
    assert "aerial of a coastal city at dawn" in meta["ai_metadata"]["prompt"]


def test_wan_generate_writes_asset_and_meta(comfy_url, tmp_path) -> None:
    client = comfyui_client.ComfyUIClient(comfy_url, poll_interval=0.05)
    target = tmp_path / "out.mp4"
    meta = wan_video.generate(
        _spec("close-up portrait of a speaker", shot_id="test-wan-001"),
        target, client=client,
    )
    assert meta["source"]["name"] == "wan-2.2"
    assert meta["ai_metadata"]["model"] == "wan-2.2"


def test_recipe_cache_skips_comfyui(comfy_url, tmp_path) -> None:
    """Second generate() with same spec should hit the AI cache and not call ComfyUI."""
    client = comfyui_client.ComfyUIClient(comfy_url, poll_interval=0.05)
    spec = _spec("aerial of mountains at sunrise")

    # First run — populates cache.
    target1 = tmp_path / "a.mp4"
    meta1 = ltx_video.generate(spec, target1, client=client)
    assert meta1["source"]["source_metadata"]["from_recipe_cache"] is False

    # Now break the mock so a second call would fail if it were attempted.
    mock.MockComfy.fail_on_submit = True
    target2 = tmp_path / "b.mp4"
    meta2 = ltx_video.generate(spec, target2, client=client)
    assert meta2["source"]["source_metadata"]["from_recipe_cache"] is True
    assert target2.exists() and target1.exists()
    # Same seed → cache hit.
    assert meta1["ai_metadata"]["seed"] == meta2["ai_metadata"]["seed"]


def test_explicit_seed_is_honoured(comfy_url, tmp_path) -> None:
    client = comfyui_client.ComfyUIClient(comfy_url, poll_interval=0.05)
    meta = ltx_video.generate(
        _spec("anything", _seed=12345),
        tmp_path / "out.mp4", client=client,
    )
    assert meta["ai_metadata"]["seed"] == 12345


def test_submit_failure_after_retries_raises(comfy_url, tmp_path) -> None:
    """Spot-style failure: submit always 500s → AIGenerationError surfaces."""
    mock.MockComfy.fail_on_submit = True
    client = comfyui_client.ComfyUIClient(comfy_url, poll_interval=0.05, submit_timeout=2)
    with pytest.raises(AIGenerationError):
        ltx_video.generate(_spec("anything"), tmp_path / "out.mp4", client=client)


def test_workflow_substitution_replaces_slots() -> None:
    """Ensure the substitution helper actually fills slots."""
    from broll.sources._ai_base import _substitute_slots
    template = {
        "1": {"class_type": "X", "inputs": {"text": "<<PROMPT>>", "seed": "<<SEED>>"}},
    }
    out = _substitute_slots(template, {"PROMPT": "hello", "SEED": 42})
    assert out["1"]["inputs"] == {"text": "hello", "seed": 42}


def test_unknown_slot_raises() -> None:
    from broll.sources._ai_base import _substitute_slots
    with pytest.raises(AIGenerationError):
        _substitute_slots({"1": {"inputs": {"x": "<<MISSING>>"}}}, {})


def test_empty_lora_slot_disables_safely() -> None:
    from broll.sources._ai_base import _substitute_slots
    template = {
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "<<LORA_0_NAME>>",
                "strength_model": "<<LORA_0_STRENGTH>>",
                "strength_clip": "<<LORA_0_STRENGTH>>",
            },
        }
    }
    out = _substitute_slots(template, {"LORA_0_NAME": "", "LORA_0_STRENGTH": 0.0})
    # Empty lora name should be replaced with "none" + 0-strength to keep node happy.
    assert out["2"]["inputs"]["lora_name"] == "none"
    assert out["2"]["inputs"]["strength_model"] == 0.0

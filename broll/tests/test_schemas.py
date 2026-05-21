"""Validate that both schemas accept good payloads and reject bad ones."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SHOT_SCHEMA = json.loads((ROOT / "schema" / "shot_spec_schema.json").read_text())
ASSET_SCHEMA = json.loads((ROOT / "schema" / "asset_meta_schema.json").read_text())


def _validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


# ── Shot spec ────────────────────────────────────────────────────────────────
def test_shot_spec_schema_is_well_formed() -> None:
    _validator(SHOT_SCHEMA)


def test_shot_spec_accepts_minimal_good_spec() -> None:
    v = _validator(SHOT_SCHEMA)
    spec = {
        "shot_id": "ep001-broll-001",
        "intent": "container ships at sea",
        "kind": "establishing",
        "duration_seconds": 4,
    }
    assert list(v.iter_errors(spec)) == []


def test_shot_spec_accepts_full_good_spec() -> None:
    v = _validator(SHOT_SCHEMA)
    spec = json.loads((ROOT.parent / "scripts" / "broll" / "test_shot.json").read_text())
    assert list(v.iter_errors(spec)) == []


@pytest.mark.parametrize(
    "mutator,reason",
    [
        (lambda s: s.pop("shot_id"), "missing shot_id"),
        (lambda s: s.update(shot_id=""), "empty shot_id"),
        (lambda s: s.update(shot_id="has spaces and !!!"), "bad shot_id pattern"),
        (lambda s: s.update(kind="not_a_kind"), "bad kind"),
        (lambda s: s.update(duration_seconds=0), "zero duration"),
        (lambda s: s.update(duration_seconds=-1), "negative duration"),
        (lambda s: s.update(format="diagonal"), "bad format"),
        (lambda s: s.update(extra_field=True), "additional property"),
    ],
)
def test_shot_spec_rejects_bad(mutator, reason) -> None:
    v = _validator(SHOT_SCHEMA)
    spec: dict = {
        "shot_id": "ep001-broll-001",
        "intent": "container ships at sea",
        "kind": "establishing",
        "duration_seconds": 4,
    }
    mutator(spec)
    assert list(v.iter_errors(spec)), f"expected validation failure: {reason}"


# ── Asset meta ───────────────────────────────────────────────────────────────
def _good_stock_meta() -> dict:
    return {
        "shot_id": "ep001-broll-001",
        "asset_path": "output/broll/ep001-broll-001.mp4",
        "kind": "stock_video",
        "source": {
            "name": "pexels",
            "version": None,
            "url": "https://www.pexels.com/video/1234567/",
            "fetched_at": "2026-05-20T14:32:00Z",
        },
        "license": {
            "type": "pexels",
            "attribution_required": False,
            "attribution_text": "Video by Jane Doe via Pexels",
            "commercial_use_ok": True,
        },
        "verification": None,
        "ai_metadata": None,
        "modifications": [],
    }


def _good_ai_meta() -> dict:
    m = _good_stock_meta()
    m["kind"] = "ai_video"
    m["source"]["name"] = "ltx-2.3"
    m["source"]["version"] = "2.3"
    m["license"] = {
        "type": "ai_generated",
        "attribution_required": False,
        "attribution_text": None,
        "commercial_use_ok": True,
    }
    m["ai_metadata"] = {
        "model": "ltx-2.3",
        "prompt": "aerial shot of canal at dawn, golden lighting",
        "seed": 12345,
        "lora_stack": [{"name": "LTX2.3_Soft_Enhance", "strength": 0.4}],
        "sampler": "euler",
        "steps": 30,
        "resolution": [1280, 720],
        "duration_seconds": 5,
    }
    return m


def test_asset_meta_schema_is_well_formed() -> None:
    _validator(ASSET_SCHEMA)


def test_asset_meta_accepts_stock_video() -> None:
    v = _validator(ASSET_SCHEMA)
    assert list(v.iter_errors(_good_stock_meta())) == []


def test_asset_meta_accepts_ai_video() -> None:
    v = _validator(ASSET_SCHEMA)
    assert list(v.iter_errors(_good_ai_meta())) == []


def test_asset_meta_rejects_stock_with_ai_metadata() -> None:
    v = _validator(ASSET_SCHEMA)
    meta = _good_stock_meta()
    meta["ai_metadata"] = _good_ai_meta()["ai_metadata"]
    assert list(v.iter_errors(meta))


def test_asset_meta_rejects_ai_without_ai_metadata() -> None:
    v = _validator(ASSET_SCHEMA)
    meta = _good_ai_meta()
    meta["ai_metadata"] = None
    assert list(v.iter_errors(meta))


def test_asset_meta_rejects_unknown_license_type() -> None:
    v = _validator(ASSET_SCHEMA)
    meta = _good_stock_meta()
    meta["license"]["type"] = "fictional_license"
    assert list(v.iter_errors(meta))

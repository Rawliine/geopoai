"""Phase-0 end-to-end smoke test against the real Pexels API.

Skipped when PEXELS_API_KEY is not set so the rest of the suite stays offline.
Network test marker keeps it out of fast loops; run with::

    pytest broll/tests/test_phase0_smoke.py -m network
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

pytestmark = pytest.mark.network


@pytest.mark.skipif(not os.environ.get("PEXELS_API_KEY"), reason="PEXELS_API_KEY not set")
def test_phase0_smoke(tmp_path, monkeypatch) -> None:
    """Run pipeline/broll.py against scripts/broll/test_shot.json, redirect output."""
    from broll.lib import asset_wrapper  # noqa: E402
    from pipeline import broll  # noqa: E402

    # Redirect output to tmp so we don't pollute the repo.
    monkeypatch.setattr(broll, "_OUTPUT_DIR", tmp_path)

    spec = json.loads((ROOT / "scripts" / "broll" / "test_shot.json").read_text())
    spec["shot_id"] = "phase0-smoke-pytest"

    meta = broll.run_shot(spec)
    assert meta["shot_id"] == "phase0-smoke-pytest"
    asset = tmp_path / "phase0-smoke-pytest.mp4"
    assert asset.exists() and asset.stat().st_size > 0
    assert asset_wrapper.meta_path_for(asset).exists()
    assert meta["source"]["name"] == "pexels"
    assert meta["license"]["commercial_use_ok"] is True

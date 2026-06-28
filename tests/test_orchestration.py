"""W20 — orchestration runner / hashing / invalidate / QC tests.

The heavy renderer + compose calls are stubbed via ctx.hooks, so the whole
episode walks offline. The committed episodes/_example/ dry episode supplies the
hand-authored brain artifacts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from orchestration import manifest as M
from orchestration import runner
from orchestration.stages import qc

_REPO = Path(__file__).resolve().parent.parent
_EXAMPLE = _REPO / "episodes" / "_example"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def episode(tmp_path):
    """A temp repo with the _example episode copied in; returns (repo, ep_id)."""
    ep_id = "_example"
    dst = tmp_path / "episodes" / ep_id
    shutil.copytree(_EXAMPLE, dst)
    return tmp_path, ep_id


def _render_hook(calls, regions_for=None, regions_dir=None):
    """A stub render_clip that records calls and fakes outputs."""
    def render_clip(entry, ctx):
        clip_id = entry["clip_id"]
        calls.append(clip_id)
        outputs = {"video": f"output/{clip_id}.mp4"}
        if regions_for and clip_id == regions_for:
            outputs["regions"] = f"output/{clip_id}.regions.json"
        return outputs
    return render_clip


# ── Full walk ────────────────────────────────────────────────────────────────

def test_full_walk_to_publish(episode):
    repo, ep_id = episode
    # a regions sidecar for the map_region clip e3
    (repo / "output").mkdir()
    (repo / "output" / "e3.regions.json").write_text(json.dumps({
        "clip_id": "e3", "format": "horizontal", "frame": [1920, 1080],
        "regions": [{"id": "media-top", "region": "top", "rect": [0, 0, 1920, 540],
                     "start": 1, "end": 5}],
    }))
    calls: list[str] = []
    hooks = {"render_clip": _render_hook(calls, regions_for="e3")}

    # walk every stage
    seen = []
    for _ in range(len(M.STAGE_SEQUENCE) + 1):
        stage, status = runner.next_stage(ep_id, repo_root=repo, hooks=hooks)
        if stage is None:
            break
        assert status == "done", f"{stage} -> {status}"
        seen.append(stage)

    assert seen == list(M.STAGE_SEQUENCE)
    manifest = M.load(M.episode_dir(repo, ep_id))
    assert all(M.get_status(manifest, s) == "done" for s in M.STAGE_SEQUENCE)
    assert manifest["qc"]["status"] == "passed"
    # ingest populated evidence + media_pool
    assert [e["id"] for e in manifest["evidence"]] == ["src1"]
    assert {m["id"] for m in manifest["media_pool"]} == {"m_region", "m_broll"}
    # every clip rendered once
    assert sorted(calls) == ["e1", "e2", "e3", "e4"]

    # map_region routed into compose media_overlays at episode time (offset 11s)
    spec = json.loads((M.episode_dir(repo, ep_id) / "compose.json").read_text())
    overlays = spec.get("media_overlays", [])
    assert len(overlays) == 1
    assert overlays[0]["start"] == 12 and overlays[0]["end"] == 16
    assert overlays[0]["region"] == "top"


def test_halt_awaits_at_first_brain_stage(tmp_path):
    """A fresh episode (no authored artifacts) halts at the first brain stage."""
    bible_default = "halt"
    manifest = M.new_manifest("geopoai", "_example", ["horizontal"], bible_default)
    M.save(M.episode_dir(tmp_path, "_example"), manifest)

    stage, status = runner.next_stage("_example", repo_root=tmp_path)
    assert (stage, status) == ("ingest", "done")  # mechanical first
    stage, status = runner.next_stage("_example", repo_root=tmp_path)
    assert stage == "angle" and status == "awaiting_brain"
    # the halt brain wrote the operator hand-off
    sd = M.stage_dir(M.episode_dir(tmp_path, "_example"), "angle")
    assert (sd / "instruction.md").exists() and (sd / "schema.json").exists()


# ── Selective re-render (T6) ─────────────────────────────────────────────────

def test_invalidate_one_clip_rerenders_only_it(episode):
    repo, ep_id = episode
    (repo / "output").mkdir()
    first: list[str] = []
    runner_hooks = {"render_clip": _render_hook(first)}
    for _ in range(len(M.STAGE_SEQUENCE) + 1):
        stage, _status = runner.next_stage(ep_id, repo_root=repo, hooks=runner_hooks)
        if stage is None:
            break
    assert sorted(first) == ["e1", "e2", "e3", "e4"]

    # invalidate one clip → render + downstream flip to pending
    flipped = runner.invalidate(ep_id, "e2", repo_root=repo)
    assert flipped == ["render", "compose", "qc", "publish"]

    second: list[str] = []
    runner.run_named(ep_id, "render", repo_root=repo, hooks={"render_clip": _render_hook(second)})
    assert second == ["e2"]  # exactly one re-render


def test_invalidate_script_flips_downstream(episode):
    repo, ep_id = episode
    flipped = runner.invalidate(ep_id, "script", repo_root=repo)
    assert flipped == list(M.STAGE_SEQUENCE[M.STAGE_SEQUENCE.index("script"):])


# ── QC rules (T4) — each fails on a fixture ──────────────────────────────────

def test_qc_callout_duplication():
    issues = qc.check_callout_duplication(
        [("Allies always pull together", "Allies always pull together now")], 0.6
    )
    assert issues and "duplicates VO" in issues[0]
    assert qc.check_callout_duplication([("PAYOFF MATRIX", "they coordinate closely")], 0.6) == []


def test_qc_pacing_gap_and_spike():
    assert qc.check_pacing([0.0, 10.0], 4.0)  # 10s gap
    assert qc.check_pacing([0.1 * i for i in range(12)], 4.0)  # density spike


def test_qc_caption_collisions_skipped_when_never():
    assert qc.check_caption_collisions("never", ["x"]) == []
    assert qc.check_caption_collisions("always", ["x"])


def test_qc_loudness_and_integrity():
    assert qc.check_loudness(-20.0, -14.0, 1.0)
    assert qc.check_loudness(-14.0, -14.0, 1.0) == []
    assert qc.check_loudness(None, -14.0, 1.0) == []
    assert qc.check_clip_integrity({"entries": [{"clip_id": "e1"}]}, [])


# ── Discipline: no show-specific content in stages/ ──────────────────────────

def test_no_genre_hardcoded_in_stages():
    stages_dir = _REPO / "orchestration" / "stages"
    for py in stages_dir.glob("*.py"):
        assert "geopoli" not in py.read_text(encoding="utf-8").lower(), py.name

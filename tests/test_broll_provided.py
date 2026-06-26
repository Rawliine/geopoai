"""Tests for operator-provided b-roll media (W27)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broll.lib import asset_wrapper, vision_verifier
from broll.lib.provided_source import ProvidedSourceError, ingest_provided, probe_media
from pipeline.broll import run_shot


def _make_test_mp4(path: Path, *, duration: float = 2.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=320x240:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr}")


@pytest.fixture
def sample_license() -> dict:
    return {
        "type": "user_provided",
        "attribution_required": True,
        "attribution_text": "Operator test clip",
        "commercial_use_ok": False,
    }


@pytest.fixture
def shot_spec() -> dict:
    return {
        "shot_id": "test-provided-001",
        "intent": "solid blue color field test clip",
        "kind": "establishing",
        "duration_seconds": 2,
    }


@pytest.fixture
def verifier() -> vision_verifier.HeuristicVerifier:
    return vision_verifier.HeuristicVerifier(threshold=0.0)


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "broll_out"


def test_local_provided_becomes_clip_with_license(
    shot_spec: dict,
    sample_license: dict,
    verifier: vision_verifier.HeuristicVerifier,
    output_dir: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "operator.mp4"
    _make_test_mp4(source, duration=2.5)
    target = output_dir / f"{shot_spec['shot_id']}.mp4"

    meta = ingest_provided(
        shot_spec,
        target,
        {"path": str(source), "license": sample_license},
        verifier_backend=verifier,
        output_dir=output_dir,
    )

    assert target.exists()
    assert meta["source"]["name"] == "provided"
    assert meta["license"]["type"] == "user_provided"
    assert meta["license"]["attribution_text"] == "Operator test clip"
    assert asset_wrapper.meta_path_for(target).exists()

    probed = probe_media(target)
    assert probed["duration"] == pytest.approx(2.5, abs=0.25)
    assert probed["width"] == 320
    assert probed["height"] == 240


def test_url_provided_becomes_clip_with_license(
    shot_spec: dict,
    sample_license: dict,
    verifier: vision_verifier.HeuristicVerifier,
    output_dir: Path,
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "serve"
    media_dir.mkdir()
    clip = media_dir / "remote.mp4"
    _make_test_mp4(clip, duration=1.5)

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(media_dir), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/remote.mp4"

    target = output_dir / f"{shot_spec['shot_id']}.mp4"
    try:
        meta = ingest_provided(
            shot_spec,
            target,
            {"url": url, "license": sample_license},
            verifier_backend=verifier,
            output_dir=output_dir,
        )
    finally:
        server.shutdown()

    assert target.exists()
    assert meta["source"]["name"] == "provided"
    assert meta["source"]["url"] == url
    assert meta["license"]["type"] == "user_provided"
    probed = probe_media(target)
    assert probed["duration"] == pytest.approx(1.5, abs=0.25)


def test_missing_license_rejected(tmp_path: Path, shot_spec: dict, output_dir: Path) -> None:
    source = tmp_path / "operator.mp4"
    _make_test_mp4(source)
    target = output_dir / f"{shot_spec['shot_id']}.mp4"

    with pytest.raises(ProvidedSourceError, match="license"):
        ingest_provided(
            shot_spec,
            target,
            {"path": str(source)},
            output_dir=output_dir,
        )


def test_junk_file_rejected_at_integrity_gate(
    tmp_path: Path,
    shot_spec: dict,
    sample_license: dict,
    output_dir: Path,
) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_text("not a video file", encoding="utf-8")
    target = output_dir / f"{shot_spec['shot_id']}.mp4"

    with pytest.raises(ProvidedSourceError, match="integrity"):
        ingest_provided(
            shot_spec,
            target,
            {"path": str(junk), "license": sample_license},
            output_dir=output_dir,
        )


def test_run_shot_provided_short_circuits_cascade(
    shot_spec: dict,
    sample_license: dict,
    verifier: vision_verifier.HeuristicVerifier,
    output_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "operator.mp4"
    _make_test_mp4(source)

    monkeypatch.setattr("pipeline.broll._OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        "broll.lib.provided_source.ingest_provided",
        lambda spec, target, provided, **kw: ingest_provided(
            spec,
            target,
            provided,
            verifier_backend=verifier,
            output_dir=output_dir,
            **{k: v for k, v in kw.items() if k != "output_dir"},
        ),
    )

    meta = run_shot(
        shot_spec,
        provided={"path": str(source), "license": sample_license},
    )

    assert meta["source"]["name"] == "provided"
    log_path = output_dir / f"{shot_spec['shot_id']}.log.json"
    log_doc = json.loads(log_path.read_text(encoding="utf-8"))
    assert log_doc["outcome"] == "provided"
    assert "cascade" not in log_doc

"""TTS client + voice-stage integration tests (no network, no model)."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from orchestration.context import StageContext
from orchestration.stages import voice
from pipeline import tts


def _unpack(body: bytes) -> dict:
    try:
        import ormsgpack
        return ormsgpack.unpackb(body)
    except ImportError:
        import msgpack
        return msgpack.unpackb(body, raw=False)


# ── client ───────────────────────────────────────────────────────────────────

def test_synthesize_posts_msgpack_and_writes_wav(tmp_path, monkeypatch):
    captured = {}

    @contextlib.contextmanager
    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = _unpack(req.data)

        class _Resp:
            def read(self_inner):
                return b"RIFFfake-wav-bytes"
        yield _Resp()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)

    out = tts.synthesize("Hello world", tmp_path / "vo.wav", url="http://tts.local:8080")

    assert out.exists() and out.read_bytes() == b"RIFFfake-wav-bytes"
    assert captured["url"] == "http://tts.local:8080/v1/tts"
    assert captured["headers"]["content-type"] == "application/msgpack"
    body = captured["body"]
    assert body["text"] == "Hello world"
    assert body["format"] == "wav"
    assert body["streaming"] is False
    assert body["references"] == []


def test_synthesize_includes_reference_voice(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"refaudio")
    captured = {}

    @contextlib.contextmanager
    def fake_urlopen(req, timeout=None):
        captured["body"] = _unpack(req.data)

        class _Resp:
            def read(self_inner):
                return b"wav"
        yield _Resp()

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    tts.synthesize("hi", tmp_path / "out.wav", url="http://x", reference_audio=ref, reference_text="sample")

    refs = captured["body"]["references"]
    assert len(refs) == 1 and refs[0]["audio"] == b"refaudio" and refs[0]["text"] == "sample"


# ── voice stage ──────────────────────────────────────────────────────────────

def _ctx(tmp_path, manifest, hooks=None):
    return StageContext(
        repo_root=tmp_path, ep_dir=tmp_path, manifest=manifest,
        bible={"thresholds": {"reading_words_per_s": 2.6}},
        brain_name="halt", hooks=hooks or {},
    )


def test_script_to_vo_text_strips_emphasis():
    m = {"script": {"beats": [{"vo_text": "The **payoff** wins."}, {"vo_text": "So they defect."}]}}
    assert voice.script_to_vo_text(m) == "The payoff wins. So they defect."


def test_voice_synthesizes_when_no_vo(tmp_path):
    seen = {}

    def synth(text, out_wav, ctx):
        seen["text"] = text
        Path(out_wav).write_bytes(b"RIFFfake")

    manifest = {"episode_id": "ep", "script": {"beats": [{"vo_text": "Hello **world**."}]}}
    voice.execute(_ctx(tmp_path, manifest, {"synthesize_vo": synth}))

    assert (tmp_path / "vo.wav").exists()
    assert seen["text"] == "Hello world."  # emphasis stripped, passed to TTS


def test_voice_verifies_existing_vo_without_synth(tmp_path):
    (tmp_path / "vo.wav").write_bytes(b"RIFFexisting")

    def synth(text, out_wav, ctx):
        raise AssertionError("synth must not be called when vo.wav already exists")

    manifest = {"episode_id": "ep", "script": {"beats": [{"vo_text": "x"}]}}
    voice.execute(_ctx(tmp_path, manifest, {"synthesize_vo": synth}))  # no raise


def test_voice_errors_when_no_text_and_no_vo(tmp_path):
    manifest = {"episode_id": "ep", "script": {"beats": []}}
    with pytest.raises(ValueError, match="no VO text"):
        voice.execute(_ctx(tmp_path, manifest))


# ── reference voice resolution ────────────────────────────────────────────────

def _voice_ctx(tmp_path, voice_cfg):
    return StageContext(
        repo_root=tmp_path, ep_dir=tmp_path, manifest={"episode_id": "ep"},
        bible={"voice": voice_cfg}, brain_name="halt", hooks={},
    )


def test_reference_from_bible_when_clip_exists(tmp_path):
    ref = tmp_path / "assets" / "voice" / "narrator.wav"
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b"RIFFref")
    ctx = _voice_ctx(tmp_path, {
        "reference_audio": "assets/voice/narrator.wav",
        "reference_text": "a calm narrator sample",
    })
    audio, text = voice._resolve_reference(ctx)
    assert audio == str(ref) and text == "a calm narrator sample"


def test_reference_falls_back_when_clip_missing(tmp_path):
    ctx = _voice_ctx(tmp_path, {"reference_audio": "assets/voice/missing.wav",
                                "reference_text": "x"})
    assert voice._resolve_reference(ctx) == (None, None)


def test_reference_none_when_unpinned(tmp_path):
    ctx = _voice_ctx(tmp_path, {})
    assert voice._resolve_reference(ctx) == (None, None)

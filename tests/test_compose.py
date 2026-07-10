"""W17 composition engine tests and acceptance demo."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from composition import captions, engine, sound, transitions  # noqa: E402


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-3000:])


def _generate_clip(
    path: Path,
    *,
    color: str,
    duration: float,
    size: str,
    moving_box: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if moving_box:
        vf = (
            f"color=c={color}:s={size}:d={duration},"
            f"drawbox=x='min(t*120\\,w-80)':y=h/3:w=80:h=80:c=white@0.95:t=fill"
        )
    else:
        vf = f"color=c={color}:s={size}:d={duration}"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            str(path),
        ]
    )


def _generate_vo(path: Path, duration: float = 6.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )


def _write_events(path: Path, clip_id: str, events: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"clip_id": clip_id, "fps": 30, "events": events}, indent=2),
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def compose_fixture_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("compose_fixtures")
    clips = root / "clips"
    _generate_clip(
        clips / "clip_a.mp4",
        color="0x1a3a5c",
        duration=2.0,
        size="1920x1080",
        moving_box=True,
    )
    _generate_clip(
        clips / "clip_b.mp4",
        color="0x2ecc71",
        duration=2.0,
        size="1920x1080",
        moving_box=True,
    )
    _generate_clip(
        clips / "clip_c.mp4",
        color="0xe74c3c",
        duration=2.0,
        size="1080x1920",
        moving_box=True,
    )
    _write_events(
        root / "events_a.json",
        "clip_a",
        [
            {"t": 0.0, "type": "camera", "phase": "start", "intensity": 0.8, "id": "cam_a", "role": "neutral"},
            {"t": 1.7, "type": "camera", "phase": "end", "intensity": 1.0, "id": "cam_a_end", "role": "neutral"},
        ],
    )
    _write_events(
        root / "events_b.json",
        "clip_b",
        [
            {"t": 0.1, "type": "camera", "phase": "start", "intensity": 1.0, "id": "cam_b", "role": "neutral"},
            {"t": 1.0, "type": "label", "phase": "peak", "intensity": 0.5, "id": "lbl", "role": "highlight"},
        ],
    )
    _write_events(
        root / "events_c.json",
        "clip_c",
        [
            {"t": 0.0, "type": "camera", "phase": "start", "intensity": 0.7, "id": "cam_c", "role": "neutral"},
        ],
    )
    _generate_vo(root / "vo.wav", duration=8.0)
    return root


@pytest.fixture
def compose_spec(compose_fixture_tree: Path) -> dict[str, Any]:
    def rel(p: Path) -> str:
        return p.as_posix()

    return {
      "episode_id": "w17_demo",
      "caption_policy": {"burn_in": "broll_only", "sidecar": False},
      "clips": [
          {
              "clip_id": "clip_a",
              "path": rel(compose_fixture_tree / "clips" / "clip_a.mp4"),
              "offset_s": 0.0,
              "events_path": rel(compose_fixture_tree / "events_a.json"),
              "renderer": "mapbox",
          },
          {
              "clip_id": "clip_b",
              "path": rel(compose_fixture_tree / "clips" / "clip_b.mp4"),
              "offset_s": 2.0,
              "events_path": rel(compose_fixture_tree / "events_b.json"),
              "renderer": "broll",
          },
          {
              "clip_id": "clip_c",
              "path": rel(compose_fixture_tree / "clips" / "clip_c.mp4"),
              "offset_s": 4.0,
              "events_path": rel(compose_fixture_tree / "events_c.json"),
              "renderer": "broll",
          },
      ],
      "transitions": [
          {"after_clip_id": "clip_a", "type": "whoosh", "duration": 0.25},
          {"after_clip_id": "clip_b", "type": "crossfade", "duration": 0.5},
      ],
      "audio": {"vo": rel(compose_fixture_tree / "vo.wav")},
      "export": {"profiles": ["yt_long", "shorts"]},
      "flags": {"captions": True, "sound": True, "grade": True},
  }


@pytest.fixture
def stub_captions_sound(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    ass_path = tmp_path / "captions.ass"

    def fake_captions_build(vo_wav, words_json, layout_jsons, tokens, fmt, **kwargs):
        ass_path.write_text(
            "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:08.00,Default,,0,0,0,,W17 test caption\n",
            encoding="utf-8",
        )
        return ass_path

    def fake_sound_build(events_jsons, offsets, vo_wav, tokens):
        mix = tmp_path / "mix.wav"
        _run(["ffmpeg", "-y", "-i", str(vo_wav), "-c:a", "pcm_s16le", str(mix)])
        return mix

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(captions, "build", fake_captions_build)
    monkeypatch.setattr(sound, "build", fake_sound_build)
    yield
    monkeypatch.undo()


def test_validate_compose_min_fixture() -> None:
    spec = json.loads(
        (_REPO / "docs" / "contracts" / "fixtures" / "compose.min.json").read_text()
    )
    engine.validate_spec(spec)


def test_validate_rejects_unknown_caption_policy() -> None:
    spec = json.loads(
        (_REPO / "docs" / "contracts" / "fixtures" / "compose.min.json").read_text()
    )
    spec["caption_policy"] = {"burn_in": "sometimes"}
    with pytest.raises(ValueError):
        engine.validate_spec(spec)


def test_legacy_flags_captions_false_means_never() -> None:
    spec = {"flags": {"captions": False}}
    policy = engine.parse_caption_policy(spec)
    assert policy["burn_in"] == "never"


def test_mux_audio_warns_when_audio_exceeds_video(monkeypatch, tmp_path, caplog) -> None:
    # audio longer than the assembled video → -shortest would cut the voice tail
    durs = {"v.mp4": 104.0, "a.wav": 107.5}
    monkeypatch.setattr(engine, "_probe_duration", lambda p: durs[Path(p).name])
    monkeypatch.setattr(engine, "_run_ffmpeg", lambda *a, **k: None)
    with caplog.at_level("WARNING"):
        engine._mux_audio(Path("v.mp4"), Path("a.wav"), tmp_path / "out.mp4")
    assert "VOICE" in caplog.text


def test_select_transition_whoosh_falls_back_without_camera() -> None:
    recipe = transitions.select_transition(
        {"clip_id": "a", "fps": 30, "events": []},
        {"clip_id": "b", "fps": 30, "events": []},
        {"type": "whoosh", "duration": 0.25},
        outgoing_duration=2.0,
        incoming_duration=2.0,
    )
    assert recipe["type"] == "crossfade"
    assert recipe.get("fallback_from") == "whoosh"


def test_select_transition_whoosh_trims_with_camera_events() -> None:
    outgoing = {
        "clip_id": "a",
        "fps": 30,
        "events": [
            {"t": 1.7, "type": "camera", "phase": "end", "intensity": 1.0, "id": "e"},
        ],
    }
    incoming = {
        "clip_id": "b",
        "fps": 30,
        "events": [
            {"t": 0.1, "type": "camera", "phase": "start", "intensity": 1.0, "id": "s"},
        ],
    }
    recipe = transitions.select_transition(
        outgoing,
        incoming,
        {"type": "whoosh", "duration": 0.25},
        outgoing_duration=2.0,
        incoming_duration=2.0,
    )
    assert recipe["type"] == "whoosh"
    assert recipe["trim_out_s"] > 0
    assert recipe["trim_in_s"] > 0


def test_compute_burn_windows_broll_only() -> None:
    spec = {
        "clips": [
            {"clip_id": "a", "path": "x.mp4", "offset_s": 0, "renderer": "mapbox"},
            {"clip_id": "b", "path": "y.mp4", "offset_s": 2, "renderer": "broll"},
        ]
    }
    timeline = [
        {"clip": spec["clips"][0], "start_s": 0.0, "duration_s": 2.0},
        {"clip": spec["clips"][1], "start_s": 2.0, "duration_s": 2.0},
    ]
    windows = engine.compute_burn_windows(
        spec,
        timeline=timeline,
        active_profile="yt_long",
        caption_policy={"burn_in": "broll_only", "sidecar": False},
    )
    assert windows == [(2.0, 4.0)]


def test_pass_skipping_grade_flag(tmp_path: Path, compose_spec: dict[str, Any], stub_captions_sound) -> None:
    compose_spec["flags"]["grade"] = False
    workdir = tmp_path / "work"
    outputs = engine.compose(
        compose_spec,
        workdir,
        repo_root=_REPO,
        keep_temp=True,
        no_grade=False,
    )
    assert outputs["yt_long"].exists()


@pytest.mark.render
def test_demo_compose_end_to_end(
    tmp_path: Path,
    compose_spec: dict[str, Any],
    stub_captions_sound,
    compose_fixture_tree: Path,
) -> None:
    episode = tmp_path / "w17_demo"
    workdir = episode / "work"
    outputs = engine.compose(
        compose_spec,
        workdir,
        repo_root=_REPO,
        keep_temp=True,
    )
    for profile in ("yt_long", "shorts"):
        final = outputs[profile]
        assert final.exists()
        assert final.stat().st_size > 10_000
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(final),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert float(probe.stdout.strip()) > 3.0

    boundary_dir = episode / "boundary_frames"
    boundary_dir.mkdir(parents=True, exist_ok=True)
    clip_a = compose_fixture_tree / "clips" / "clip_a.mp4"
    clip_b = compose_fixture_tree / "clips" / "clip_b.mp4"
    _dump_frame(clip_a, 1.65, boundary_dir / "whoosh_out_before.png")
    _dump_frame(clip_b, 0.15, boundary_dir / "whoosh_in_before.png")
    assembled = workdir / "assembled.mp4"
    _dump_frame(assembled, 1.85, boundary_dir / "whoosh_assembled_after.png")

    report = {
        "outputs": {k: str(v) for k, v in outputs.items()},
        "intermediates": sorted(p.name for p in workdir.iterdir()),
        "boundary_frames": sorted(p.name for p in boundary_dir.iterdir()),
    }
    report_path = episode / "compose_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def _dump_frame(video: Path, t: float, out_png: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(out_png),
        ]
    )


def test_shorts_refused_for_horizontal_only(tmp_path: Path, compose_fixture_tree: Path) -> None:
    from composition import export as export_mod

    horizontal = compose_fixture_tree / "clips" / "clip_a.mp4"
    profile = export_mod.profiles(engine.load_tokens())["shorts"]
    with pytest.raises(ValueError, match="horizontal-only"):
        export_mod.encode_profile(
            horizontal,
            tmp_path / "out.mp4",
            profile,
            clip_paths=[horizontal],
            repo_root=_REPO,
        )

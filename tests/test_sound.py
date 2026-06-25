"""W16 sound pass — rules engine, mix, and acceptance tests."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition import sound  # noqa: E402


@pytest.fixture
def tokens() -> dict:
    return json.loads((ROOT / "config" / "design_tokens.json").read_text())


@pytest.fixture
def palette(tokens: dict) -> dict:
    return sound._load_palette(tokens)


def _write_events(path: Path, clip_id: str, events: list[dict]) -> Path:
    path.write_text(
        json.dumps({"clip_id": clip_id, "fps": 30, "events": events}, indent=2) + "\n"
    )
    return path


def _event(
    t: float,
    type_: str,
    *,
    phase: str = "start",
    intensity: float = 0.8,
    id_: str | None = None,
) -> dict:
    return {
        "t": t,
        "type": type_,
        "phase": phase,
        "intensity": intensity,
        "id": id_ or f"{type_}_{t}",
    }


def _segment_rms_db(wav: Path, start: float, duration: float) -> float:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(wav),
            "-af",
            "astats=metadata=1:reset=1",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    for line in proc.stderr.splitlines():
        if "RMS level dB" in line:
            return float(line.split(":", 1)[1].strip())
    raise RuntimeError(f"RMS level not found in ffmpeg output: {proc.stderr[-400:]}")


def test_collect_events_shifts_by_offsets(tmp_path: Path) -> None:
    first = _write_events(
        tmp_path / "a.events.json",
        "clip_a",
        [_event(1.0, "camera", id_="a_cam")],
    )
    second = _write_events(
        tmp_path / "b.events.json",
        "clip_b",
        [_event(0.5, "label", phase="peak", id_="b_label")],
    )
    merged = sound.collect_events([first, second], [2.0, 10.0])
    assert [(e.clip_id, e.t, e.type) for e in merged] == [
        ("clip_a", 3.0, "camera"),
        ("clip_b", 10.5, "label"),
    ]


def test_family_cooldown_drops_later_cue(palette: dict) -> None:
    events = [
        sound.CollectedEvent("c", 0.0, 0.0, "label", "peak", 0.9, "first"),
        sound.CollectedEvent("c", 1.0, 1.0, "chapter", "start", 1.0, "second"),
    ]
    plan = sound.plan_cues(events, palette)
    assert len(plan.placed) == 1
    assert plan.placed[0].event_id == "first"
    assert any(d.reason == "family_cooldown" for d in plan.dropped)


def test_global_density_cap(palette: dict) -> None:
    cap = int(palette["density_cap_per_10s"])
    types = ("camera", "label", "counter", "fill", "arrow", "image", "highlight", "border")
    events = [
        sound.CollectedEvent(
            "c",
            float(i) * 0.35,
            float(i) * 0.35,
            types[i % len(types)],
            "start" if types[i % len(types)] != "fill" else "peak",
            0.7,
            f"evt_{i}",
        )
        for i in range(cap + 4)
    ]
    plan = sound.plan_cues(events, palette)
    assert len(plan.placed) == cap
    assert any(d.reason == "global_density_cap" for d in plan.dropped)


def test_simultaneous_dedupe_keeps_highest_intensity(palette: dict) -> None:
    events = [
        sound.CollectedEvent("c", 1.0, 1.0, "camera", "start", 0.5, "low"),
        sound.CollectedEvent("c", 1.05, 1.05, "arrow", "start", 0.95, "high"),
    ]
    plan = sound.plan_cues(events, palette)
    assert len(plan.placed) == 1
    assert plan.placed[0].event_id == "high"
    assert any(d.reason == "simultaneous_dedupe" for d in plan.dropped)


def test_plan_cues_is_deterministic(palette: dict) -> None:
    events = sound.collect_events([ROOT / "docs/contracts/fixtures/events.min.json"], [0.0])
    first = sound.plan_cues(events, palette)
    second = sound.plan_cues(events, palette)
    assert first.placed == second.placed
    assert first.dropped == second.dropped


def test_cues_json_byte_identical_across_runs(tmp_path: Path, tokens: dict) -> None:
    vo = tmp_path / "vo.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=3", str(vo)],
        check=True,
        capture_output=True,
    )
    events = [ROOT / "docs/contracts/fixtures/events.min.json"]
    sound.build(events, [0.0], vo, tokens)
    first = (tmp_path / "mix.cues.json").read_bytes()
    sound.build(events, [0.0], vo, tokens)
    second = (tmp_path / "mix.cues.json").read_bytes()
    assert first == second


def _excess_power_db(mix: Path, vo: Path, start: float, duration: float) -> float:
    mix_db = _segment_rms_db(mix, start, duration)
    vo_db = _segment_rms_db(vo, start, duration)
    mix_lin = 10 ** (mix_db / 10)
    vo_lin = 10 ** (vo_db / 10)
    return 10 * math.log10(max(mix_lin - vo_lin, 1e-12))


def test_vo_duck_lowers_sfx_during_speech(tmp_path: Path, tokens: dict, palette: dict) -> None:
    vo_loud = tmp_path / "vo_loud.wav"
    vo_silent = tmp_path / "vo_silent.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=3,volume=0.8", str(vo_loud)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=3", str(vo_silent)],
        check=True,
        capture_output=True,
    )
    events_path = _write_events(
        tmp_path / "duck.events.json",
        "duck_clip",
        [_event(1.5, "camera", intensity=0.95, id_="whoosh")],
    )
    events = sound.collect_events([events_path], [0.0])
    plan = sound.plan_cues(events, palette)
    sfx = tmp_path / "sfx.wav"
    sound._render_sfx_bus(plan.placed, 3.0, sfx)
    mix_loud = tmp_path / "mix_loud.wav"
    mix_silent = tmp_path / "mix_silent.wav"
    duck_db = float(tokens["sound"]["vo_duck_db"])
    sound._mix_vo_and_buses(vo_loud, sfx, None, duck_db, mix_loud)
    sound._mix_vo_and_buses(vo_silent, sfx, None, duck_db, mix_silent)
    bleed_loud = _excess_power_db(mix_loud, vo_loud, 1.45, 0.15)
    bleed_silent = _excess_power_db(mix_silent, vo_silent, 1.45, 0.15)
    assert bleed_loud < bleed_silent - 3.0


def test_demo_fixture_mix_audible_and_loudness(tmp_path: Path, tokens: dict) -> None:
    vo = tmp_path / "vo.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=180:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=4",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first,volume=0.8",
            str(vo),
        ],
        check=True,
        capture_output=True,
    )
    mix = sound.build([ROOT / "docs/contracts/fixtures/events.min.json"], [0.0], vo, tokens)
    assert mix.exists() and mix.stat().st_size > 10_000
    cues = json.loads((tmp_path / "mix.cues.json").read_text())
    families = {c["family"] for c in cues["placed"]}
    assert "whoosh" in families
    assert cues["bed"] is not None

    measure = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(mix),
            "-af",
            "loudnorm=I=-14:dual_mono=true:print_format=json",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert measure.returncode == 0
    loudnorm_json = sound._parse_loudnorm_json(measure.stderr)
    input_i = float(loudnorm_json["input_i"])
    assert -14.5 <= input_i <= -13.5, loudnorm_json

    whoosh_window = _segment_rms_db(mix, 0.0, 0.25)
    bed_window = _segment_rms_db(mix, 0.5, 0.5)
    assert whoosh_window > bed_window - 6.0

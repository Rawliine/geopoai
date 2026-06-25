"""W15 caption lane — chunker, placement, burn windows, demo burn-in."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.captions import (
    Chunk,
    Word,
    build,
    chunk_words,
    load_words,
    place_chunks,
    write_ass,
)
from tools.tokens import load_tokens

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = FIXTURES.parent.parent


@pytest.fixture
def tokens() -> dict:
    return load_tokens()


def test_chunker_punctuation_and_cadence(tokens: dict) -> None:
    words = [
        Word("Hello", 0.0, 0.3, 1.0),
        Word("world.", 0.3, 0.6, 1.0),
        Word("Next", 0.7, 0.9, 1.0),
        Word("beat", 0.9, 1.1, 1.0),
        Word("here", 1.1, 1.3, 1.0),
    ]
    chunks = chunk_words(words, tokens)
    assert len(chunks) == 2
    assert chunks[0].words == ("Hello", "world.")
    assert len(chunks[1].words) <= 3


def test_chunker_keeps_number_with_unit(tokens: dict) -> None:
    words = [
        Word("fifty", 0.0, 0.2, 1.0),
        Word("kilometers", 0.2, 0.5, 1.0),
        Word("east", 0.5, 0.7, 1.0),
    ]
    chunks = chunk_words(words, tokens)
    assert any("fifty" in c.words and "kilometers" in c.words for c in chunks)


def test_chunker_emphasis_from_script(tokens: dict) -> None:
    script = "The **front line** shifted overnight."
    words = load_words(FIXTURES / "words_golden.json", script)
    chunks = chunk_words(words, tokens, script_text=script)
    emph_chunks = [c for c in chunks if any(c.emphasis)]
    assert emph_chunks
    assert "front" in emph_chunks[0].words


def test_placement_relocates_when_default_occupied(tokens: dict) -> None:
    words = load_words(FIXTURES / "words_golden.json")
    chunks = chunk_words(words, tokens)
    layout = FIXTURES / "layout_occupied_vertical.json"
    placements = place_chunks(chunks, tokens, "vertical", [layout], [0.0])
    default_band = tuple(tokens["safe_areas"]["vertical"]["caption_band"])
    relocated = [
        idx for idx, (name, band) in placements.items() if band != default_band
    ]
    assert relocated, "expected at least one chunk away from occupied default band"


def test_hysteresis_avoids_flip_flop(tokens: dict, tmp_path: Path) -> None:
    """Persistent lower occupancy keeps captions in the same relocated band."""
    layout_doc = {
        "clip_id": "steady",
        "format": "vertical",
        "sample_hz": 1,
        "frames": [
            {
                "t": 0.0,
                "boxes": [
                    {
                        "id": "lower_callout",
                        "kind": "callout",
                        "x": 0.1,
                        "y": 0.76,
                        "w": 0.8,
                        "h": 0.14,
                    }
                ],
            }
        ],
    }
    layout_path = tmp_path / "layout_steady.json"
    layout_path.write_text(json.dumps(layout_doc), encoding="utf-8")
    chunks = [
        Chunk(("one",), (False,), 0.0, 1.0),
        Chunk(("two",), (False,), 1.0, 2.0),
        Chunk(("three",), (False,), 2.0, 3.0),
    ]
    placements = place_chunks(chunks, tokens, "vertical", [layout_path], [0.0])
    bands = [placements[i][0] for i in range(len(chunks))]
    assert bands[0] != "default"
    assert len(set(bands)) == 1


def test_burn_windows_filter_ass_not_srt(tokens: dict, tmp_path: Path) -> None:
    words_path = FIXTURES / "words_golden.json"
    words = load_words(words_path)
    chunks = chunk_words(words, tokens)
    ass_path = tmp_path / "test.ass"
    srt_path = tmp_path / "test.srt"
    write_ass(chunks, tokens, "vertical", ass_path, burn_windows=[(0.0, 2.5)])
    from composition.captions import write_srt

    write_srt(chunks, srt_path)
    ass_text = ass_path.read_text(encoding="utf-8")
    srt_text = srt_path.read_text(encoding="utf-8")
    ass_dialogues = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    assert len(ass_dialogues) < len(chunks)
    assert srt_text.count("-->") == len(chunks)


def test_build_accepts_compose_fixture_layout(tokens: dict, tmp_path: Path) -> None:
    layout = REPO / "docs/contracts/fixtures/layout.min.json"
    words = FIXTURES / "words_golden.json"
    vo = FIXTURES / "vo_sample.wav"
    out = build(
        vo,
        words,
        [layout],
        tokens,
        "horizontal",
        clip_offsets=[0.0],
        output_dir=tmp_path,
    )
    assert out.suffix == ".ass"
    assert out.is_file()


@pytest.mark.render
def test_demo_burned_vertical_clip(tokens: dict, tmp_path: Path) -> None:
    """Burn captions into 9:16 solid b-roll clips; capture placement screenshots."""
    words_path = FIXTURES / "vo_sample.words.json"
    if not words_path.is_file():
        subprocess.run(
            [
                "conda",
                "run",
                "-n",
                "geopo",
                "python",
                str(REPO / "tools/align_vo.py"),
                str(FIXTURES / "vo_sample.wav"),
                "--script",
                str(FIXTURES / "vo_sample_beats.txt"),
            ],
            check=True,
            cwd=REPO,
        )
    script = (FIXTURES / "vo_sample_beats.txt").read_text(encoding="utf-8")
    vo = FIXTURES / "vo_sample.wav"
    out_dir = FIXTURES / "demo_output"
    out_dir.mkdir(exist_ok=True)
    empty_layout = FIXTURES / "layout_clear_vertical.json"
    occupied_layout = FIXTURES / "layout_occupied_vertical.json"

    for label, layout in [("default", empty_layout), ("relocated", occupied_layout)]:
        ass_path = build(
            vo,
            words_path,
            [layout],
            tokens,
            "vertical",
            clip_offsets=[0.0],
            burn_windows=[(0.0, 6.0)],
            script_text=script,
            output_dir=out_dir / label,
        )
        base_video = out_dir / label / "broll_base.mp4"
        burned = out_dir / label / "caption_demo_9x16.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x0e1116:s=1080x1920:d=6",
                "-i",
                str(vo),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(base_video),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(base_video),
                "-vf",
                f"subtitles={ass_path}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                str(burned),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "1.8",
                "-i",
                str(burned),
                "-frames:v",
                "1",
                str(out_dir / f"{label}_placement.png"),
            ],
            check=True,
            capture_output=True,
        )
        assert burned.stat().st_size > 10_000
        assert (out_dir / f"{label}_placement.png").stat().st_size > 1000

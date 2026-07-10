"""VO timing map — voice as master clock (orchestration/timing.py)."""

from __future__ import annotations

from orchestration import timing


def _words(n, step=0.5, dur=0.4):
    return [{"word": f"w{i}", "start": round(i * step, 3),
             "end": round(i * step + dur, 3), "confidence": 1.0} for i in range(n)]


def test_beat_spans_tile_the_audio():
    beats = [
        {"beat_id": "b1", "vo_text": "one two three four five."},   # 5 words
        {"beat_id": "b2", "vo_text": "six seven eight nine ten."},  # 5 words
    ]
    words = _words(10)
    t = timing.build_timing(beats, words)
    b1, b2 = t["beats"]["b1"], t["beats"]["b2"]
    # contiguous + covers the whole audio
    assert b1["start"] == 0.0
    assert b1["end"] <= b2["start"] + 1e-6
    assert abs(b2["end"] - t["vo_duration"]) < 1e-6
    assert t["vo_duration"] == words[-1]["end"]


def test_sentences_recorded_per_beat():
    beats = [{"beat_id": "b1", "vo_text": "First short. Second longer sentence here."}]
    t = timing.build_timing(beats, _words(6))
    sents = t["beats"]["b1"]["sentences"]
    assert len(sents) == 2
    assert sents[0]["text"].startswith("First")
    assert all(s["duration"] >= 0 for s in sents)


def test_derive_even_split_when_one_sentence_many_clips():
    beats = [{"beat_id": "b1", "vo_text": "one two three four five six seven eight"}]
    t = timing.build_timing(beats, _words(8))
    entries = [
        {"clip_id": "c1", "beat_id": "b1"},
        {"clip_id": "c2", "beat_id": "b1"},
    ]
    d = timing.derive_clip_durations(entries, t)
    # two clips, one sentence -> even split of the beat span
    assert set(d) == {"c1", "c2"}
    assert abs(d["c1"] - d["c2"]) < 1e-6
    assert abs((d["c1"] + d["c2"]) - t["beats"]["b1"]["duration"]) < 0.05


def test_derive_sentence_groups_across_clips():
    beats = [{"beat_id": "b1", "vo_text": "Alpha one two. Bravo three four. Charlie five six."}]
    t = timing.build_timing(beats, _words(9))
    entries = [
        {"clip_id": "c1", "beat_id": "b1"},
        {"clip_id": "c2", "beat_id": "b1"},
        {"clip_id": "c3", "beat_id": "b1"},
    ]
    d = timing.derive_clip_durations(entries, t)
    assert set(d) == {"c1", "c2", "c3"}
    # each clip owns a real, positive span
    assert all(v > 0 for v in d.values())


def test_clip_durations_tile_the_full_audio():
    # Two beats, two clips each, with inter-word gaps (pauses). Durations must
    # tile the whole audio — no pause dropped — so the video matches the VO.
    beats = [
        {"beat_id": "b1", "vo_text": "Alpha one. Bravo two."},
        {"beat_id": "b2", "vo_text": "Charlie three. Delta four."},
    ]
    words = _words(8)  # step 0.5 / dur 0.4 -> 0.1s gap between every word
    t = timing.build_timing(beats, words)
    entries = [
        {"clip_id": "c1", "beat_id": "b1"},
        {"clip_id": "c2", "beat_id": "b1"},
        {"clip_id": "c3", "beat_id": "b2"},
        {"clip_id": "c4", "beat_id": "b2"},
    ]
    d = timing.derive_clip_durations(entries, t)
    assert set(d) == {"c1", "c2", "c3", "c4"}
    assert abs(sum(d.values()) - t["vo_duration"]) < 1e-6


def test_build_timing_uses_measured_audio_length():
    # The measured file is longer than the last aligned word (trailing decay).
    beats = [{"beat_id": "b1", "vo_text": "one two three."}]
    words = _words(3)
    t = timing.build_timing(beats, words, audio_duration=3.0)
    assert t["vo_duration"] == 3.0
    assert t["beats"]["b1"]["end"] == 3.0
    assert t["beats"]["b1"]["sentences"][-1]["end"] == 3.0
    # default (no audio_duration) still uses the last aligned word end
    t0 = timing.build_timing(beats, words)
    assert t0["vo_duration"] == words[-1]["end"]


def test_last_clip_absorbs_trailing_audio():
    beats = [{"beat_id": "b1", "vo_text": "one two three."}]
    t = timing.build_timing(beats, _words(3), audio_duration=5.0)
    d = timing.derive_clip_durations([{"clip_id": "c1", "beat_id": "b1"}], t)
    assert abs(d["c1"] - 5.0) < 1e-6


def test_derive_skips_beats_without_timing():
    t = {"vo_duration": 5.0, "beats": {"b1": {"start": 0, "end": 5, "duration": 5,
                                              "sentences": [{"text": "x", "start": 0,
                                                             "end": 5, "duration": 5}]}}}
    entries = [{"clip_id": "c1", "beat_id": "b1"}, {"clip_id": "c2", "beat_id": "bX"}]
    d = timing.derive_clip_durations(entries, t)
    assert "c1" in d and "c2" not in d

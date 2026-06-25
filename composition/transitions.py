"""Clip boundary transitions — W17 implements."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

WHOOSH_FALLBACK_CROSSFADE_S = 0.25
WHOOSH_TRIM_FRAMES = 6
MOTION_NEAR_BOUNDARY_S = 0.75


def select_transition(
    outgoing_events: dict[str, Any] | None,
    incoming_events: dict[str, Any] | None,
    spec_transition: dict[str, Any],
    *,
    outgoing_duration: float,
    incoming_duration: float,
    fps: float = 30.0,
) -> dict[str, Any]:
    """Resolve the ffmpeg transition recipe for a clip boundary."""
    ttype = spec_transition["type"]
    if ttype == "cut":
        return {"type": "cut"}

    if ttype == "crossfade":
        duration = float(spec_transition.get("duration", 0.5))
        return {"type": "crossfade", "duration": duration}

    if ttype != "whoosh":
        raise ValueError(f"unknown transition type: {ttype!r}")

    duration = float(spec_transition.get("duration", WHOOSH_FALLBACK_CROSSFADE_S))
    outgoing_motion = _motion_window_near_end(outgoing_events, outgoing_duration)
    incoming_motion = _motion_window_near_start(incoming_events, incoming_duration)

    if outgoing_motion is None or incoming_motion is None:
        return {
            "type": "crossfade",
            "duration": WHOOSH_FALLBACK_CROSSFADE_S,
            "fallback_from": "whoosh",
        }

    trim_s = WHOOSH_TRIM_FRAMES / fps
    return {
        "type": "whoosh",
        "duration": duration,
        "trim_out_s": min(trim_s, outgoing_duration * 0.25),
        "trim_in_s": min(trim_s, incoming_duration * 0.25),
        "boundary_camera": {
            "type": "camera",
            "phase": "peak",
            "intensity": 1.0,
            "id": "whoosh_cut",
            "role": "neutral",
        },
    }


def _motion_window_near_end(
    events_doc: dict[str, Any] | None,
    duration: float,
) -> tuple[float, float] | None:
    if not events_doc:
        return None
    fps = float(events_doc.get("fps", 30))
    window_start = max(0.0, duration - MOTION_NEAR_BOUNDARY_S)
    cameras = [
        e
        for e in events_doc.get("events", [])
        if e.get("type") == "camera" and e.get("phase") in {"end", "peak"}
    ]
    for event in reversed(cameras):
        t = float(event["t"])
        if t >= window_start:
            span = 1.0 / fps * WHOOSH_TRIM_FRAMES
            return (max(0.0, t - span), min(duration, t + span))
    return None


def _motion_window_near_start(
    events_doc: dict[str, Any] | None,
    duration: float,
) -> tuple[float, float] | None:
    if not events_doc:
        return None
    fps = float(events_doc.get("fps", 30))
    window_end = min(duration, MOTION_NEAR_BOUNDARY_S)
    cameras = [
        e
        for e in events_doc.get("events", [])
        if e.get("type") == "camera" and e.get("phase") in {"start", "peak"}
    ]
    for event in cameras:
        t = float(event["t"])
        if t <= window_end:
            span = 1.0 / fps * WHOOSH_TRIM_FRAMES
            return (max(0.0, t - span), min(duration, t + span))
    return None


def _run_ffmpeg(cmd: list[str], *, label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stderr[-4000:] if result.stderr else ""
        raise RuntimeError(f"ffmpeg failed during {label}:\n{tail}")


def _probe_codec(path: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _trim_clip(
    src: Path,
    dst: Path,
    *,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> None:
    cmd = ["ffmpeg", "-y", "-ss", f"{start_s:.6f}", "-i", str(src)]
    if end_s is not None:
        cmd.extend(["-to", f"{(end_s - start_s):.6f}"])
    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(dst)])
    _run_ffmpeg(cmd, label="trim_clip")


def _xfade_pair(
    left: Path,
    right: Path,
    dst: Path,
    *,
    duration: float,
    offset: float,
) -> None:
    left_w, left_h = _probe_video_size(left)
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(left),
            "-i",
            str(right),
            "-filter_complex",
            (
                f"[1:v]scale={left_w}:{left_h}:force_original_aspect_ratio=decrease,"
                f"pad={left_w}:{left_h}:(ow-iw)/2:(oh-ih)/2[rs];"
                f"[0:v][rs]xfade=transition=fade:duration={duration:.6f}:offset={offset:.6f}[v]"
            ),
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dst),
        ],
        label="xfade",
    )


def _probe_video_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def _concat_demuxer(paths: list[Path], dst: Path) -> None:
    list_path = dst.with_suffix(".concat.txt")
    lines = [f"file '{p.resolve().as_posix()}'" for p in paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    codecs = {_probe_codec(p) for p in paths}
    if len(codecs) == 1 and "h264" in next(iter(codecs)):
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(dst),
            ],
            label="concat_copy",
        )
    else:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(dst),
            ],
            label="concat_encode",
        )


def assemble_timeline(
    clip_paths: list[Path],
    clip_specs: list[dict[str, Any]],
    events_docs: list[dict[str, Any] | None],
    durations: dict[str, float],
    transitions_by_clip: dict[str, dict[str, Any]],
    workdir: Path,
    *,
    light_leak: bool = False,
) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build assembled video and episode timeline metadata."""
    workdir.mkdir(parents=True, exist_ok=True)
    if not clip_paths:
        raise ValueError("compose spec must include at least one clip")

    segments: list[Path] = [clip_paths[0]]
    segment_durations = [durations[clip_specs[0]["clip_id"]]]
    timeline: list[dict[str, Any]] = []
    merged_events: list[dict[str, Any]] = []
    boundary_meta: list[dict[str, Any]] = []

    episode_t = 0.0
    timeline.append(
        {
            "clip": clip_specs[0],
            "start_s": episode_t,
            "duration_s": segment_durations[0],
        }
    )
    episode_t += segment_durations[0]

    for idx in range(1, len(clip_paths)):
        prev_spec = clip_specs[idx - 1]
        clip_spec = clip_specs[idx]
        clip_path = clip_paths[idx]
        events_doc = events_docs[idx]
        prev_events = events_docs[idx - 1]

        spec_tr = transitions_by_clip.get(
            prev_spec["clip_id"],
            {"after_clip_id": prev_spec["clip_id"], "type": "cut"},
        )
        recipe = select_transition(
            prev_events,
            events_doc,
            spec_tr,
            outgoing_duration=segment_durations[-1],
            incoming_duration=durations[clip_spec["clip_id"]],
            fps=float((events_doc or prev_events or {}).get("fps", 30)),
        )
        boundary_meta.append({"after_clip_id": prev_spec["clip_id"], "recipe": recipe})

        if recipe["type"] == "whoosh":
            trim_out = recipe["trim_out_s"]
            trim_in = recipe["trim_in_s"]
            trimmed_prev = workdir / f"whoosh_out_{idx}.mp4"
            _trim_clip(
                segments[-1],
                trimmed_prev,
                start_s=0.0,
                end_s=segment_durations[-1] - trim_out,
            )
            segments[-1] = trimmed_prev
            segment_durations[-1] -= trim_out
            timeline[-1]["duration_s"] = segment_durations[-1]

            trimmed_in = workdir / f"whoosh_in_{idx}.mp4"
            raw_duration = durations[clip_spec["clip_id"]]
            _trim_clip(
                clip_path,
                trimmed_in,
                start_s=trim_in,
                end_s=raw_duration,
            )
            segments.append(trimmed_in)
            seg_dur = raw_duration - trim_in
            segment_durations.append(seg_dur)

            boundary_t = timeline[-1]["start_s"] + timeline[-1]["duration_s"]
            merged_events.append(
                {
                    "clip_id": f"whoosh_{prev_spec['clip_id']}_to_{clip_spec['clip_id']}",
                    "fps": float((events_doc or prev_events or {}).get("fps", 30)),
                    "events": [dict(recipe["boundary_camera"])],
                    "episode_t": boundary_t,
                }
            )
            timeline.append(
                {
                    "clip": clip_spec,
                    "start_s": boundary_t,
                    "duration_s": seg_dur,
                }
            )
            episode_t = boundary_t + seg_dur

        elif recipe["type"] == "crossfade":
            duration = recipe["duration"]
            offset = max(0.0, segment_durations[-1] - duration)
            xfade_out = workdir / f"xfade_{idx}.mp4"
            _xfade_pair(segments[-1], clip_path, xfade_out, duration=duration, offset=offset)
            new_duration = segment_durations[-1] + _probe_duration(clip_path) - duration
            segments[-1] = xfade_out
            segment_durations[-1] = new_duration
            timeline[-1]["duration_s"] = new_duration
            timeline[-1]["clip"] = {
                **timeline[-1]["clip"],
                "merged_with": clip_spec["clip_id"],
            }
            episode_t = timeline[-1]["start_s"] + new_duration

        else:
            segments.append(clip_path)
            seg_dur = durations[clip_spec["clip_id"]]
            segment_durations.append(seg_dur)
            timeline.append(
                {
                    "clip": clip_spec,
                    "start_s": episode_t,
                    "duration_s": seg_dur,
                }
            )
            episode_t += seg_dur

    if light_leak:
        leaked = workdir / "light_leak.mp4"
        _apply_light_leak(segments[-1], leaked, workdir)
        segments[-1] = leaked

    assembled = workdir / "assembled.mp4"
    _concat_demuxer(segments, assembled)
    return assembled, timeline, merged_events, boundary_meta


def _apply_light_leak(src: Path, dst: Path, workdir: Path) -> None:
    """Optional screen-blend light leak — off unless spec enables it."""
    leak = workdir / "light_leak_overlay.mp4"
    if not leak.exists():
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", str(src), "-vf", "format=yuv420p", "-an", str(leak)],
            label="light_leak_src",
        )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-i",
            str(leak),
            "-filter_complex",
            "[0:v][1:v]blend=all_mode=screen:all_opacity=0.35[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dst),
        ],
        label="light_leak",
    )


def write_merged_events(
    synthetic: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    events_docs: list[dict[str, Any] | None],
    out_path: Path,
) -> list[Path]:
    """Write per-clip shifted events plus synthetic boundary cameras."""
    paths: list[Path] = []
    for entry, events_doc in zip(timeline, events_docs, strict=False):
        if events_doc is None:
            continue
        shifted = {
            "clip_id": events_doc["clip_id"],
            "fps": events_doc["fps"],
            "events": [],
        }
        offset = entry["start_s"]
        for event in events_doc.get("events", []):
            item = dict(event)
            item["t"] = float(event["t"]) + offset
            shifted["events"].append(item)
        path = out_path.parent / f"{events_doc['clip_id']}_shifted.json"
        path.write_text(json.dumps(shifted, indent=2), encoding="utf-8")
        if path not in paths:
            paths.append(path)

    for synth in synthetic:
        path = out_path.parent / f"{synth['clip_id']}.json"
        payload = {
            "clip_id": synth["clip_id"],
            "fps": synth["fps"],
            "events": [
                {**synth["events"][0], "t": synth["episode_t"]},
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        paths.append(path)

    out_path.write_text(json.dumps({"paths": [str(p) for p in paths]}, indent=2), encoding="utf-8")
    return paths

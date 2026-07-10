"""Episode compose orchestrator — W17 implements against compose.schema.json."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema

from composition import captions, export, sound, transitions

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _REPO_ROOT / "docs" / "contracts" / "compose.schema.json"
_TOKENS_PATH = _REPO_ROOT / "config" / "design_tokens.json"

_BURN_IN_VALUES = frozenset({"never", "broll_only", "shorts_only", "always"})


def load_tokens(path: Path | None = None) -> dict[str, Any]:
    tokens_path = path or _TOKENS_PATH
    return json.loads(tokens_path.read_text(encoding="utf-8"))


def _schema_validate(spec: dict[str, Any]) -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    sanitized = deepcopy(spec)
    sanitized.pop("caption_policy", None)
    for clip in sanitized.get("clips", []):
        clip.pop("renderer", None)
        clip.pop("captions", None)
    jsonschema.validate(instance=sanitized, schema=schema)


def parse_caption_policy(spec: dict[str, Any]) -> dict[str, Any]:
    """Return normalized caption policy with defaults."""
    raw = spec.get("caption_policy")
    if raw is None:
        policy = {"burn_in": "broll_only", "sidecar": False}
    elif isinstance(raw, dict):
        policy = {
            "burn_in": raw.get("burn_in", "broll_only"),
            "sidecar": bool(raw.get("sidecar", False)),
        }
    else:
        raise ValueError("caption_policy must be an object when present")

    if policy["burn_in"] not in _BURN_IN_VALUES:
        raise ValueError(f"unsupported caption_policy.burn_in: {policy['burn_in']!r}")

    if spec.get("flags", {}).get("captions") is False:
        policy = {**policy, "burn_in": "never"}
    return policy


def validate_spec(spec: dict[str, Any]) -> None:
    """Validate compose spec against schema plus relaxed caption_policy."""
    _schema_validate(spec)
    parse_caption_policy(spec)


def _resolve(repo_root: Path, path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _run_ffmpeg(cmd: list[str], *, label: str) -> None:
    log.info("ffmpeg [%s]: %s", label, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stderr[-4000:] if result.stderr else ""
        raise RuntimeError(f"ffmpeg failed during {label}:\n{tail}")


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


def _load_events(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _clip_durations(clips: list[dict[str, Any]], repo_root: Path) -> dict[str, float]:
    durations: dict[str, float] = {}
    for clip in clips:
        mp4 = _resolve(repo_root, clip["path"])
        durations[clip["clip_id"]] = _probe_duration(mp4)
    return durations


def _transition_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for entry in spec.get("transitions", []):
        mapping[entry["after_clip_id"]] = entry
    return mapping


def compute_burn_windows(
    spec: dict[str, Any],
    *,
    timeline: list[dict[str, Any]],
    active_profile: str,
    caption_policy: dict[str, Any],
) -> list[tuple[float, float]]:
    """Episode-time intervals where ASS burn-in is active."""
    if caption_policy["burn_in"] == "never":
        return []

    windows: list[tuple[float, float]] = []
    for entry in timeline:
        clip = entry["clip"]
        start = entry["start_s"]
        end = start + entry["duration_s"]
        renderer = clip.get("renderer")
        if renderer is None:
            path = _resolve(_REPO_ROOT, clip["path"]).as_posix()
            renderer = "broll" if "/broll/" in path else "mapbox"

        if clip.get("captions") is False:
            continue

        burn_in = caption_policy["burn_in"]
        include = (
            burn_in == "always"
            or (burn_in == "broll_only" and renderer == "broll")
            or (burn_in == "shorts_only" and active_profile == "shorts")
        )
        if include:
            windows.append((start, end))
    return windows


def _ass_time_to_seconds(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, cs = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(cs) / 100.0


def _seconds_to_ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    ss, cc = divmod(cs, 100)
    mm, ss = divmod(ss, 60)
    hh, mm = divmod(mm, 60)
    return f"{hh:d}:{mm:02d}:{ss:02d}.{cc:02d}"


def _filter_ass_to_windows(ass_path: Path, windows: list[tuple[float, float]], out_path: Path) -> Path:
    if not windows:
        out_path.write_text(
            "[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text\n",
            encoding="utf-8",
        )
        return out_path

    lines = ass_path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    for line in lines:
        if not line.startswith("Dialogue:"):
            kept.append(line)
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            kept.append(line)
            continue
        start = _ass_time_to_seconds(parts[1])
        end = _ass_time_to_seconds(parts[2])
        for win_start, win_end in windows:
            if end > win_start and start < win_end:
                clip_start = max(start, win_start)
                clip_end = min(end, win_end)
                parts[1] = _seconds_to_ass_time(clip_start)
                parts[2] = _seconds_to_ass_time(clip_end)
                kept.append(",".join(parts))
                break
    out_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return out_path


def _burn_ass(
    video_in: Path,
    ass_path: Path,
    video_out: Path,
    windows: list[tuple[float, float]],
) -> None:
    filtered = video_out.with_suffix(".filtered.ass")
    _filter_ass_to_windows(ass_path, windows, filtered)
    escaped = filtered.as_posix().replace(":", r"\:").replace("'", r"\'")
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_in),
            "-vf",
            f"subtitles='{escaped}'",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(video_out),
        ],
        label="burn_ass",
    )


# If the assembled video runs longer than the audio by more than this, `-shortest`
# would silently drop the tail — a symptom of an un-trimmed clip. Surface it loudly.
_MUX_TRUNCATE_WARN_S = 1.0


def _mux_audio(video_in: Path, audio_in: Path, video_out: Path) -> None:
    v_dur = _probe_duration(video_in)
    a_dur = _probe_duration(audio_in)
    if v_dur - a_dur > _MUX_TRUNCATE_WARN_S:
        log.warning(
            "mux_audio: assembled video (%.2fs) exceeds audio (%.2fs) by %.2fs — "
            "`-shortest` will drop %.2fs of video. Likely an un-trimmed clip; "
            "check broll durations and the storyboard timing map.",
            v_dur, a_dur, v_dur - a_dur, v_dur - a_dur,
        )
    elif a_dur - v_dur > _MUX_TRUNCATE_WARN_S:
        log.warning(
            "mux_audio: audio (%.2fs) exceeds assembled video (%.2fs) by %.2fs — "
            "`-shortest` will drop %.2fs of VOICE off the tail. The clip durations "
            "sum short of the VO; check the storyboard timing map (derive_clip_"
            "durations should tile the full audio).",
            a_dur, v_dur, a_dur - v_dur, a_dur - v_dur,
        )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_in),
            "-i",
            str(audio_in),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(video_out),
        ],
        label="mux_audio",
    )


def _apply_grade(
    video_in: Path,
    video_out: Path,
    tokens: dict[str, Any],
) -> None:
    grading = tokens.get("grading", {})
    filters: list[str] = []
    lut = grading.get("lut")
    if lut:
        lut_path = _resolve(_REPO_ROOT, lut)
        filters.append(f"lut3d={lut_path}")
    vignette = grading.get("vignette_opacity")
    if vignette:
        filters.append(f"vignette=angle=PI/4:mode=forward:eval=frame:dither=1")
    grain = grading.get("grain_opacity")
    if grain:
        filters.append(f"noise=alls={int(grain * 100)}:allf=t+u")

    if not filters:
        shutil.copy2(video_in, video_out)
        return

    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_in),
            "-vf",
            ",".join(filters),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(video_out),
        ],
        label="grade",
    )


def _emit_sidecar_srt(workdir: Path) -> Path:
    """Minimal placeholder sidecar when burn is skipped."""
    srt_path = workdir / "captions.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n[sidecar]\n",
        encoding="utf-8",
    )
    return srt_path


def compose(
    compose_spec: dict[str, Any],
    workdir: Path,
    *,
    tokens: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    keep_temp: bool = False,
    no_grade: bool = False,
) -> dict[str, Path]:
    """Assemble clips per *compose_spec* into per-profile final MP4s."""
    validate_spec(compose_spec)
    root = repo_root or _REPO_ROOT
    tokens = tokens or load_tokens()
    flags = compose_spec.get("flags", {})
    caption_policy = parse_caption_policy(compose_spec)
    skip_captions = flags.get("captions") is False or caption_policy["burn_in"] == "never"
    skip_sound = flags.get("sound") is False
    skip_grade = flags.get("grade") is False or no_grade

    clips = compose_spec["clips"]
    durations = _clip_durations(clips, root)
    transitions_by_clip = _transition_map(compose_spec)

    clip_paths = [_resolve(root, c["path"]) for c in clips]
    events_docs = [
        _load_events(_resolve(root, c["events_path"]) if c.get("events_path") else None)
        for c in clips
    ]

    assembled_path, timeline, merged_events, boundary_meta = transitions.assemble_timeline(
        clip_paths,
        clips,
        events_docs,
        durations,
        transitions_by_clip,
        workdir,
        light_leak=bool(compose_spec.get("light_leak", False)),
    )

    # W26 — composite reserved-region media boxes onto the assembled timeline
    # (post; never decoded in the browser). Once, before the per-profile loop.
    media_overlays = compose_spec.get("media_overlays", [])
    if media_overlays and flags.get("media") is not False:
        from composition import media_overlay

        fw, fh = _probe_video_size(assembled_path)
        assembled_path = media_overlay.apply_media_overlays(
            assembled_path,
            media_overlays,
            workdir,
            tokens=tokens,
            repo_root=root,
            frame_size=(fw, fh),
        )

    profile_defs = export.profiles(tokens)
    export_profiles = compose_spec["export"]["profiles"]
    outputs: dict[str, Path] = {}

    vo_path = _resolve(root, compose_spec["audio"]["vo"])
    words_path = vo_path.with_suffix(".words.json")
    layout_paths = [
        _resolve(root, c["layout_path"])
        for c in clips
        if c.get("layout_path")
    ]
    layout_offsets = [
        entry["start_s"]
        for entry, c in zip(timeline, clips)
        if c.get("layout_path")
    ]

    for profile_name in export_profiles:
        profile = profile_defs[profile_name]
        fmt = profile["format"]
        burn_windows = compute_burn_windows(
            compose_spec,
            timeline=timeline,
            active_profile=profile_name,
            caption_policy=caption_policy,
        )

        staged = assembled_path
        ass_path: Path | None = None

        if not skip_captions:
            ass_path = captions.build(
                vo_path,
                words_path if words_path.exists() else None,
                layout_paths,
                tokens,
                fmt,
                clip_offsets=layout_offsets,
                burn_windows=burn_windows,
                caption_policy=caption_policy,
            )
            captioned = workdir / f"captions_{profile_name}.mp4"
            if ass_path.exists() and burn_windows:
                _burn_ass(staged, ass_path, captioned, burn_windows)
                staged = captioned
        elif caption_policy["sidecar"]:
            _emit_sidecar_srt(workdir)

        if not skip_sound:
            # collect_events wants clip-local events.json paired 1:1 with the
            # clip's episode offset (it shifts each itself) — feed it those,
            # not the pre-shifted merged output.
            sound_pairs = [
                (_resolve(root, c["events_path"]), entry["start_s"])
                for c, entry in zip(clips, timeline)
                if c.get("events_path")
            ]
            if sound_pairs:
                event_paths = [p for p, _ in sound_pairs]
                sound_offsets = [o for _, o in sound_pairs]
                mix_path = sound.build(event_paths, sound_offsets, vo_path, tokens)
                muxed = workdir / f"muxed_{profile_name}.mp4"
                _mux_audio(staged, mix_path, muxed)
                staged = muxed
            else:
                muxed = workdir / f"muxed_{profile_name}.mp4"
                _mux_audio(staged, vo_path, muxed)
                staged = muxed
        else:
            muxed = workdir / f"muxed_{profile_name}.mp4"
            _mux_audio(staged, vo_path, muxed)
            staged = muxed

        graded = workdir / f"graded_{profile_name}.mp4"
        if skip_grade:
            shutil.copy2(staged, graded)
        else:
            _apply_grade(staged, graded, tokens)

        episode_dir = workdir.parent
        final_path = episode_dir / f"final_{profile_name}.mp4"
        export.encode_profile(
            graded,
            final_path,
            profile,
            clip_paths=clip_paths,
            repo_root=root,
        )
        outputs[profile_name] = final_path

    if not keep_temp:
        for child in workdir.iterdir():
            if child.is_file():
                child.unlink()

    return outputs

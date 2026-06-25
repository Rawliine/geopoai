"""Sound pass — events.json → SFX mix + bed + loudness (W16)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SIMULTANEOUS_WINDOW_S = 0.08
_TRIGGER_PHASES = frozenset({"start", "peak"})
_SWELL_PEAK_TYPES = frozenset({"fill", "border", "highlight", "model"})
_BED_DUCK_DB = 3.0
_BED_FADE_S = 1.5
_BED_DUCK_HALF_WINDOW_S = 0.35

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_asset(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return _repo_root() / path


@dataclass(frozen=True)
class CollectedEvent:
    clip_id: str
    t: float
    t_local: float
    type: str
    phase: str
    intensity: float
    id: str
    role: str | None = None


@dataclass
class SFXCue:
    t: float
    family: str
    file: Path
    gain_db: float
    pitch_ratio: float
    clip_id: str
    event_id: str
    event_type: str
    intensity: float
    phase: str
    source: str = "event"


@dataclass
class DroppedCue:
    t: float
    family: str
    event_id: str
    event_type: str
    intensity: float
    reason: str


@dataclass
class BedSpec:
    file: Path
    gain_db: float
    fade_s: float = _BED_FADE_S
    duck_db: float = _BED_DUCK_DB


@dataclass
class CuePlan:
    placed: list[SFXCue] = field(default_factory=list)
    dropped: list[DroppedCue] = field(default_factory=list)
    bed: BedSpec | None = None
    bed_duck_windows: list[tuple[float, float]] = field(default_factory=list)


def _load_palette(tokens: dict[str, Any]) -> dict[str, Any]:
    sound_tokens = tokens.get("sound", tokens)
    manifest = sound_tokens.get("palette_manifest", "assets/sfx/palette.json")
    palette_path = _resolve_asset(manifest)
    return json.loads(palette_path.read_text())


def collect_events(events_jsons: list[Path], offsets: list[float]) -> list[CollectedEvent]:
    """Load per-clip events.json, shift by clip offsets, merge into episode time."""
    if len(events_jsons) != len(offsets):
        raise ValueError("events_jsons and offsets must have the same length")

    collected: list[CollectedEvent] = []
    for path, offset in zip(events_jsons, offsets):
        data = json.loads(Path(path).read_text())
        clip_id = data["clip_id"]
        for ev in data["events"]:
            collected.append(
                CollectedEvent(
                    clip_id=clip_id,
                    t=float(ev["t"]) + float(offset),
                    t_local=float(ev["t"]),
                    type=ev["type"],
                    phase=ev["phase"],
                    intensity=float(ev["intensity"]),
                    id=ev["id"],
                    role=ev.get("role"),
                )
            )
    collected.sort(key=lambda e: (e.t, e.clip_id, e.id))
    return collected


def _family_entries(palette: dict[str, Any], family: str) -> list[dict[str, Any]]:
    spec = palette["families"][family]
    entries = [{"file": spec["file"], "gain_db": spec["gain_db"]}]
    entries.extend(spec.get("variants", []))
    return entries


def _pick_variant(
    entries: list[dict[str, Any]],
    clip_id: str,
    t: float,
    family: str,
) -> dict[str, Any]:
    idx = int.from_bytes(_seed_bytes(clip_id, t, family, "variant")[:4], "big") % len(entries)
    return entries[idx]


def _seed_bytes(clip_id: str, t: float, family: str, kind: str) -> bytes:
    key = f"{clip_id}:{t:.6f}:{family}:{kind}"
    return hashlib.sha256(key.encode()).digest()


def _jitter(clip_id: str, t: float, family: str) -> tuple[float, float]:
    """Deterministic tiny gain (dB) and pitch-ratio offsets."""
    h = _seed_bytes(clip_id, t, family, "jitter")
    gain_offset = (h[0] / 255.0 - 0.5) * 0.6
    pitch_cents = (h[1] / 255.0 - 0.5) * 20.0
    pitch_ratio = 2.0 ** (pitch_cents / 1200.0)
    return gain_offset, pitch_ratio


def _intensity_gain(base_gain_db: float, intensity: float) -> float:
    return base_gain_db + (intensity - 0.7) * 6.0


def _should_trigger(event: CollectedEvent, family: str) -> bool:
    if event.phase == "end":
        return False
    if family == "swell" and event.type in _SWELL_PEAK_TYPES:
        return event.phase == "peak"
    return event.phase in _TRIGGER_PHASES


def _event_family(event: CollectedEvent, palette: dict[str, Any]) -> str | None:
    event_map: dict[str, str] = palette.get("event_map", {})
    family = event_map.get(event.type)
    if family == "ambient_bed":
        return None
    return family


def _candidate_cues(events: list[CollectedEvent], palette: dict[str, Any]) -> list[SFXCue]:
    candidates: list[SFXCue] = []
    for event in events:
        family = _event_family(event, palette)
        if family is None or not _should_trigger(event, family):
            continue
        entries = _family_entries(palette, family)
        pick = _pick_variant(entries, event.clip_id, event.t, family)
        if pick["file"] == "TODO_CURATE":
            continue
        gain_offset, pitch_ratio = _jitter(event.clip_id, event.t, family)
        gain_db = _intensity_gain(float(pick["gain_db"]), event.intensity) + gain_offset
        candidates.append(
            SFXCue(
                t=event.t,
                family=family,
                file=_resolve_asset(pick["file"]),
                gain_db=gain_db,
                pitch_ratio=pitch_ratio,
                clip_id=event.clip_id,
                event_id=event.id,
                event_type=event.type,
                intensity=event.intensity,
                phase=event.phase,
            )
        )
    candidates.sort(key=lambda c: (c.t, c.family, c.event_id))
    return candidates


def _dedupe_simultaneous(candidates: list[SFXCue]) -> tuple[list[SFXCue], list[DroppedCue]]:
    if not candidates:
        return [], []
    kept: list[SFXCue] = []
    dropped: list[DroppedCue] = []
    cluster: list[SFXCue] = [candidates[0]]
    for cue in candidates[1:]:
        if cue.t - cluster[0].t <= _SIMULTANEOUS_WINDOW_S:
            cluster.append(cue)
            continue
        winner = max(cluster, key=lambda c: (c.intensity, -c.t, c.event_id))
        for item in cluster:
            if item is winner:
                kept.append(item)
            else:
                dropped.append(
                    DroppedCue(
                        t=item.t,
                        family=item.family,
                        event_id=item.event_id,
                        event_type=item.event_type,
                        intensity=item.intensity,
                        reason="simultaneous_dedupe",
                    )
                )
        cluster = [cue]
    winner = max(cluster, key=lambda c: (c.intensity, -c.t, c.event_id))
    for item in cluster:
        if item is winner:
            kept.append(item)
        else:
            dropped.append(
                DroppedCue(
                    t=item.t,
                    family=item.family,
                    event_id=item.event_id,
                    event_type=item.event_type,
                    intensity=item.intensity,
                    reason="simultaneous_dedupe",
                )
            )
    kept.sort(key=lambda c: (c.t, c.family, c.event_id))
    return kept, dropped


def _count_in_window(times: list[float], center_t: float, window_s: float = 10.0) -> int:
    start = center_t - window_s
    return sum(1 for t in times if start < t <= center_t)


def _apply_density_and_cooldown(
    candidates: list[SFXCue],
    palette: dict[str, Any],
) -> tuple[list[SFXCue], list[DroppedCue]]:
    global_cap = int(palette.get("density_cap_per_10s", 6))
    families = palette.get("families", {})
    placed: list[SFXCue] = []
    dropped: list[DroppedCue] = []
    placed_times: list[float] = []
    family_last_t: dict[str, float] = {}
    family_times: dict[str, list[float]] = {}

    for cue in candidates:
        spec = families.get(cue.family, {})
        cooldown_s = float(spec.get("cooldown_s", 0.0))
        family_cap = int(spec.get("max_per_10s", global_cap))
        last_t = family_last_t.get(cue.family)
        if last_t is not None and cue.t - last_t < cooldown_s:
            dropped.append(
                DroppedCue(
                    t=cue.t,
                    family=cue.family,
                    event_id=cue.event_id,
                    event_type=cue.event_type,
                    intensity=cue.intensity,
                    reason="family_cooldown",
                )
            )
            continue
        if _count_in_window(placed_times, cue.t) >= global_cap:
            dropped.append(
                DroppedCue(
                    t=cue.t,
                    family=cue.family,
                    event_id=cue.event_id,
                    event_type=cue.event_type,
                    intensity=cue.intensity,
                    reason="global_density_cap",
                )
            )
            continue
        fam_times = family_times.setdefault(cue.family, [])
        if _count_in_window(fam_times, cue.t) >= family_cap:
            dropped.append(
                DroppedCue(
                    t=cue.t,
                    family=cue.family,
                    event_id=cue.event_id,
                    event_type=cue.event_type,
                    intensity=cue.intensity,
                    reason="family_density_cap",
                )
            )
            continue
        placed.append(cue)
        placed_times.append(cue.t)
        fam_times.append(cue.t)
        family_last_t[cue.family] = cue.t
    return placed, dropped


def plan_cues(events: list[CollectedEvent], palette: dict[str, Any]) -> CuePlan:
    """Map events to SFX cues and apply restraint rules."""
    candidates = _candidate_cues(events, palette)
    deduped, dedupe_drops = _dedupe_simultaneous(candidates)
    placed, rule_drops = _apply_density_and_cooldown(deduped, palette)
    return CuePlan(placed=placed, dropped=dedupe_drops + rule_drops)


def _bed_spec(palette: dict[str, Any]) -> BedSpec | None:
    spec = palette["families"]["ambient_bed"]
    entries = _family_entries(palette, "ambient_bed")
    for entry in entries:
        if entry["file"] != "TODO_CURATE":
            return BedSpec(
                file=_resolve_asset(entry["file"]),
                gain_db=float(entry["gain_db"]),
            )
    main = spec.get("file")
    if main and main != "TODO_CURATE":
        return BedSpec(file=_resolve_asset(main), gain_db=float(spec["gain_db"]))
    return None


def _existing_swell_keys(plan: CuePlan) -> set[tuple[str, float, str]]:
    return {(c.clip_id, c.t, c.event_id) for c in plan.placed if c.family == "swell"}


def _add_swell_peak_cues(
    plan: CuePlan,
    events: list[CollectedEvent],
    palette: dict[str, Any],
) -> None:
    swell_keys = _existing_swell_keys(plan)
    extras: list[SFXCue] = []
    for event in events:
        if event.type not in _SWELL_PEAK_TYPES or event.phase != "peak":
            continue
        key = (event.clip_id, event.t, event.id)
        if key in swell_keys:
            continue
        entries = _family_entries(palette, "swell")
        pick = _pick_variant(entries, event.clip_id, event.t, "swell")
        if pick["file"] == "TODO_CURATE":
            continue
        gain_offset, pitch_ratio = _jitter(event.clip_id, event.t, "swell")
        gain_db = _intensity_gain(float(pick["gain_db"]), event.intensity) + gain_offset
        extras.append(
            SFXCue(
                t=event.t,
                family="swell",
                file=_resolve_asset(pick["file"]),
                gain_db=gain_db,
                pitch_ratio=pitch_ratio,
                clip_id=event.clip_id,
                event_id=event.id,
                event_type=event.type,
                intensity=event.intensity,
                phase=event.phase,
                source="swell_peak",
            )
        )
    if not extras:
        return
    merged = plan.placed + extras
    merged.sort(key=lambda c: (c.t, c.family, c.event_id))
    deduped, dedupe_drops = _dedupe_simultaneous(merged)
    placed, rule_drops = _apply_density_and_cooldown(deduped, palette)
    plan.placed = placed
    plan.dropped.extend(dedupe_drops + rule_drops)


def _chapter_duck_windows(events: list[CollectedEvent]) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for event in events:
        if event.type != "chapter":
            continue
        if event.phase not in _TRIGGER_PHASES:
            continue
        start = max(0.0, event.t - _BED_DUCK_HALF_WINDOW_S)
        end = event.t + _BED_DUCK_HALF_WINDOW_S
        windows.append((start, end))
    return windows


def add_bed_and_swells(
    plan: CuePlan,
    events: list[CollectedEvent],
    palette: dict[str, Any],
) -> CuePlan:
    """Attach ambient bed metadata, swell peaks, and chapter duck windows."""
    _add_swell_peak_cues(plan, events, palette)
    plan.bed = _bed_spec(palette)
    plan.bed_duck_windows = _chapter_duck_windows(events)
    return plan


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return float(result.stdout.strip())


def _episode_duration(vo_wav: Path, plan: CuePlan, pad_s: float = 0.75) -> float:
    vo_dur = _probe_duration(vo_wav)
    cue_end = max((c.t for c in plan.placed), default=0.0) + pad_s
    return max(vo_dur, cue_end, 1.0)


def _render_sfx_bus(cues: list[SFXCue], duration_s: float, out_path: Path) -> None:
    if not cues:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=48000:cl=stereo:d={duration_s:.3f}",
                str(out_path),
            ]
        )
        return

    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for idx, cue in enumerate(cues):
        inputs.extend(["-i", str(cue.file)])
        delay_ms = int(round(cue.t * 1000.0))
        gain = _db_to_linear(cue.gain_db)
        label = f"c{idx}"
        filters.append(
            f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"asetrate=48000*{cue.pitch_ratio:.6f},aresample=48000,"
            f"volume={gain:.6f},adelay={delay_ms}|{delay_ms}[{label}]"
        )
        labels.append(f"[{label}]")
    mix_inputs = "".join(labels)
    filters.append(
        f"{mix_inputs}amix=inputs={len(cues)}:duration=longest:dropout_transition=0:normalize=0,"
        f"apad,atrim=0:{duration_s:.3f}[sfx]"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[sfx]",
            str(out_path),
        ]
    )


def _bed_volume_expression(spec: BedSpec, duck_windows: list[tuple[float, float]]) -> str:
    base = _db_to_linear(spec.gain_db)
    duck_lin = _db_to_linear(-spec.duck_db)
    if not duck_windows:
        return f"{base:.8f}"
    factors = [
        f"if(between(t,{start:.3f},{end:.3f}),{duck_lin:.8f},1)" for start, end in duck_windows
    ]
    return f"{base:.8f}*{'*'.join(factors)}"


def _render_bed(
    spec: BedSpec,
    duck_windows: list[tuple[float, float]],
    duration_s: float,
    out_path: Path,
) -> None:
    fade_out_start = max(0.0, duration_s - spec.fade_s)
    vol_expr = _bed_volume_expression(spec, duck_windows)
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(spec.file),
            "-t",
            f"{duration_s:.3f}",
            "-af",
            (
                f"afade=t=in:st=0:d={spec.fade_s:.3f},"
                f"afade=t=out:st={fade_out_start:.3f}:d={spec.fade_s:.3f},"
                f"volume='{vol_expr}'"
            ),
            str(out_path),
        ]
    )


def _mix_vo_and_buses(
    vo_wav: Path,
    sfx_wav: Path,
    bed_wav: Path | None,
    vo_duck_db: float,
    out_path: Path,
) -> None:
    duck_ratio = max(2.0, abs(vo_duck_db) / 2.0)
    if bed_wav is not None:
        filter_complex = (
            "[1:a][2:a]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[sfxbed];"
            f"[sfxbed][0:a]sidechaincompress=threshold=0.02:ratio={duck_ratio:.1f}:"
            "attack=8:release=220:level_sc=1:mix=1[ducked];"
            "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(vo_wav),
                "-i",
                str(sfx_wav),
                "-i",
                str(bed_wav),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                str(out_path),
            ]
        )
        return

    filter_complex = (
        f"[1:a][0:a]sidechaincompress=threshold=0.02:ratio={duck_ratio:.1f}:"
        "attack=8:release=220:level_sc=1:mix=1[ducked];"
        "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(vo_wav),
            "-i",
            str(sfx_wav),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            str(out_path),
        ]
    )


def _parse_loudnorm_json(stderr: str) -> dict[str, Any]:
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if not match:
        raise RuntimeError(f"loudnorm JSON not found in ffmpeg output: {stderr[-500:]}")
    return json.loads(match.group(0))


def _loudnorm_two_pass(input_wav: Path, target_lufs: float, out_path: Path) -> dict[str, Any]:
    measure = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(input_wav),
            "-af",
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:dual_mono=true:print_format=json",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if measure.returncode != 0:
        raise RuntimeError(measure.stderr.strip() or measure.stdout.strip())
    stats = _parse_loudnorm_json(measure.stderr)
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_wav),
            "-af",
            (
                f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:dual_mono=true:"
                f"measured_I={stats['input_i']}:"
                f"measured_TP={stats['input_tp']}:"
                f"measured_LRA={stats['input_lra']}:"
                f"measured_thresh={stats['input_thresh']}:"
                f"offset={stats['target_offset']}:linear=true:print_format=summary"
            ),
            str(out_path),
        ]
    )
    return stats


def _cue_to_dict(cue: SFXCue) -> dict[str, Any]:
    data = asdict(cue)
    data["file"] = str(cue.file)
    return data


def write_cues_json(plan: CuePlan, path: Path) -> None:
    payload = {
        "placed": [_cue_to_dict(c) for c in plan.placed],
        "dropped": [asdict(d) for d in plan.dropped],
        "bed": asdict(plan.bed) if plan.bed else None,
        "bed_duck_windows": plan.bed_duck_windows,
    }
    if payload["bed"]:
        payload["bed"]["file"] = str(plan.bed.file)  # type: ignore[index]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def mix_episode(
    vo_wav: Path,
    plan: CuePlan,
    palette: dict[str, Any],
    tokens: dict[str, Any],
) -> Path:
    """Render mix.wav (VO + SFX + bed) and mix.cues.json beside the VO."""
    sound_tokens = tokens.get("sound", tokens)
    vo_duck_db = float(sound_tokens.get("vo_duck_db", -6))
    target_lufs = float(sound_tokens.get("target_lufs", -14))
    vo_wav = Path(vo_wav)
    out_dir = vo_wav.parent
    mix_path = out_dir / "mix.wav"
    cues_path = out_dir / "mix.cues.json"
    duration_s = _episode_duration(vo_wav, plan)

    with tempfile.TemporaryDirectory(prefix="geopo-sound-") as tmp:
        tmp_dir = Path(tmp)
        sfx_path = tmp_dir / "sfx.wav"
        pre_master = tmp_dir / "pre_master.wav"
        _render_sfx_bus(plan.placed, duration_s, sfx_path)
        bed_path: Path | None = None
        if plan.bed is not None:
            bed_path = tmp_dir / "bed.wav"
            _render_bed(plan.bed, plan.bed_duck_windows, duration_s, bed_path)
        _mix_vo_and_buses(vo_wav, sfx_path, bed_path, vo_duck_db, pre_master)
        _loudnorm_two_pass(pre_master, target_lufs, mix_path)

    write_cues_json(plan, cues_path)
    return mix_path


def build(
    events_jsons: list[Path],
    offsets: list[float],
    vo_wav: Path,
    tokens: dict[str, Any],
) -> Path:
    """Mix SFX cues from clip events into a single episode waveform."""
    palette = _load_palette(tokens)
    events = collect_events(events_jsons, offsets)
    plan = plan_cues(events, palette)
    plan = add_bed_and_swells(plan, events, palette)
    return mix_episode(vo_wav, plan, palette, tokens)

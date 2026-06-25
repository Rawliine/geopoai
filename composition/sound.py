"""Sound pass — events.json → SFX mix + bed + loudness (W16)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SIMULTANEOUS_WINDOW_S = 0.08
_TRIGGER_PHASES = frozenset({"start", "peak"})
_SWELL_PEAK_TYPES = frozenset({"fill", "border", "highlight", "model"})

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
class CuePlan:
    placed: list[SFXCue] = field(default_factory=list)
    dropped: list[DroppedCue] = field(default_factory=list)
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


def build(
    events_jsons: list[Path],
    offsets: list[float],
    vo_wav: Path,
    tokens: dict[str, Any],
) -> Path:
    """Mix SFX cues from clip events into a single episode waveform."""
    raise NotImplementedError("composition.sound.build is implemented in W16")

"""Sound pass — events.json → SFX mix + bed + loudness (W16)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def build(
    events_jsons: list[Path],
    offsets: list[float],
    vo_wav: Path,
    tokens: dict[str, Any],
) -> Path:
    """Mix SFX cues from clip events into a single episode waveform."""
    raise NotImplementedError("composition.sound.build is implemented in W16")

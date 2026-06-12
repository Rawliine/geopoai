# W16 — Automatic sound pass: events.json → SFX mix + bed + loudness

Branch: `agents/w16-sound` · Depends on: W02 (contracts, SFX palette,
composition stubs). Develop against `docs/contracts/fixtures/`.

## Goal
Sound design generated from render events — never authored in scene JSON.
Restraint as brand: cooldowns and density caps; the genre whoosh-spams,
we don't.

## Allowlist
composition/sound.py · assets/sfx/palette.json (curation only) ·
tests/test_sound.py (new)

## Checklist

### T1 — Event collection
Implement `sound.build(events_jsons, offsets, vo_wav, tokens) -> mix_wav`:
load per-clip events.json, shift by clip offsets into episode time, merge.

### T2 — Mapping + rules engine
events → SFX cues via `assets/sfx/palette.json` families
(whoosh ← camera, impact ← chapter/label-slam, tick ← counter/stat,
swell ← fill/border, sting ← insight/callout):
- per-family cooldown (palette field) — drop later cue;
- global density cap: max N cues per 10s window (palette field, default 6);
- simultaneous cues (±80ms): keep highest intensity only;
- intensity → gain: `gain_db + (intensity - 0.7) * 6`;
- deterministic variation: tiny pitch/gain jitter seeded by clip_id+t
  (same input → identical output, always).

### T3 — Bed + swells
Ambient bed (palette `ambient_bed`) under the full episode at low level
with fade-in/out; swell family additionally triggered by advanceFront /
fill events with phase peaks. Bed ducks −3 dB under chapter impacts.

### T4 — Mix
Assemble with ffmpeg filter_complex (adelay per cue + amix) or pydub —
choose, justify, pin. VO is the priority bus: sidechain-duck the SFX+bed
bus under VO by `tokens.sound.vo_duck_db`. Master to
`tokens.sound.target_lufs` (ffmpeg loudnorm two-pass). Output: single
`mix.wav` (VO + SFX + bed) plus a `mix.cues.json` debug listing of every
placed/dropped cue with reasons.

### T5 — Palette curation
Replace `TODO_CURATE` markers in assets/sfx/palette.json with final picks
from provisioned packs; keep total ≤15 files; one comment per pick on
character ("short airy whoosh, no bass tail"). Brand rule in file header:
restraint over spectacle.

### T6 — Tests
Synthetic events fixture → assert: cooldown drops, density cap, dedupe,
determinism (two runs byte-identical cues.json), duck applied (RMS of SFX
bus lower during VO segments).

## Out of scope
engine/export wiring (W17 calls `sound.build`) · events emission (renderers).

## Acceptance
`pytest tests/test_sound.py` green; demo: fixture events + any speech wav →
mix.wav where (a) whoosh audible on camera event, (b) bed present,
(c) loudness measures −14±0.5 LUFS (`ffmpeg -af loudnorm=print_format=json`
output in report).

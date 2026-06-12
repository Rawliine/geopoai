# W17 — Composition engine: assembly, transitions, grading, exports

Branch: `agents/w17-compose` · Depends on: W02. Calls captions/sound via the
frozen stub signatures — develop against fixtures; full integration happens
at the lead's integration step.

## Goal
The final-video factory: ordered clips → transitions → caption burn →
sound mix → grade → per-platform exports. Everything driven by a compose
spec (docs/contracts/compose.schema.json).

## Allowlist
composition/engine.py · composition/transitions.py · composition/export.py ·
pipeline/compose.py (new CLI) · tests/test_compose.py (new)

## Checklist

### T1 — CLI + spec
`python pipeline/compose.py <compose.json> <out_name>`: validate spec
against schema, orchestrate the passes, write
`output/episodes/<out_name>/final_<profile>.mp4`. Workdir with intermediate
artifacts kept (`--keep-temp`) for debugging.

### T2 — Assembly + transitions (transitions.py)
- `cut`: plain concat (re-encode once at the end only — use concat demuxer
  when codecs match).
- `crossfade`: ffmpeg xfade, duration from spec.
- `whoosh`: camera-motion cut — trim N frames of motion from the outgoing
  clip's end and the incoming clip's start so the cut lands mid-motion
  (read camera events with phase end/start from the clips' events.json to
  find motion windows; fall back to crossfade 0.25s when no camera event
  near the boundary). Emits a synthetic `camera` event at the boundary into
  the merged event stream so W16 places the whoosh sound exactly on the cut.
- Optional light-leak overlay on transition (asset from provisioned packs,
  screen blend, off by default — spec flag).

### T3 — Pass pipeline (engine.py)
Order: assemble video → captions.build → burn ASS → sound.build →
mux mix.wav → grade. Grade: if `tokens.grading.lut` set, apply lut3d;
always available `--no-grade`. Each pass idempotent and individually
skippable via spec flags (`captions: false` for long-form CC route).

### T4 — Export profiles (export.py)
From tokens + spec: `yt_long` 1920×1080, `shorts` 1080×1920 (also used for
TikTok/Reels). Encoder: h264_nvenc when available, libx264 fallback
(mirror map_renderer/runner.py's detection — read it, reimplement locally,
do not import across layers). Audio AAC 192k. Vertical source clips pass
through; horizontal-only episodes refuse `shorts` profile with a clear
error (no auto-crop in this lane — backlog).

### T5 — Tests + demo
test_compose.py: spec validation, transition selection logic (mocked
clips), pass skipping. Demo: 3 small clips (generate solid-color +
moving-box test clips with ffmpeg in a fixture script, with hand-written
events.json) through cut/crossfade/whoosh + captions fixture + sound
fixture → playable final mp4, screenshots of each boundary in report.

## Out of scope
captions.py / sound.py internals · renderer changes · orchestration ·
auto-crop horizontal→vertical.

## Acceptance
Demo compose runs end-to-end producing both profiles; `--keep-temp` shows
each intermediate; pytest green; whoosh boundary demonstrably trims motion
frames (frame dumps before/after cut in report).

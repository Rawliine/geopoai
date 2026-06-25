# W15 — Captions: forced alignment → styled ASS → policy-driven burn-in

Branch: `agents/w15-captions` · Depends on: W02 (contracts + tokens +
composition stubs). Integrates with real layout.json after W10/W13 merge —
develop against `docs/contracts/fixtures/`.

## Goal
Word-level captions from VO audio: 1–3 word chunks, brand-styled, occupancy-
aware placement that never covers content. **Burn-in is policy-driven** (see
`caption_policy` below); default **`broll_only`** — map/manim clips carry
comprehension via authored callouts/labels; burned captions cover clips with
no text layer (b-roll). Sidecar `.srt` when `sidecar: true` (YouTube CC).
Captions are TRANSCRIPT; callouts are COMPRESSION — captions never replace
or duplicate the callout role.

## Caption policy (composition layer — independent of render safe areas)

Captions are a **separate post layer**, toggled by episode policy — **not**
coupled to `scene.safe_areas.caption_band` (layout reservation during render).
An operator sets policy in the show bible or per-episode manifest **before**
the brain runs `script`; W20 propagates it into the compose spec; W17 passes
burn/suppress windows into `captions.build()`. Renderers never read this policy.

```jsonc
"caption_policy": {
  "burn_in": "never | shorts_only | broll_only | always",  // default: broll_only
  "sidecar": true
}
```

| `burn_in` | Burned ASS on final video |
|---|---|
| `never` | No burn-in; alignment + `.srt` only when `sidecar: true` |
| `shorts_only` | Burn only when exporting the `shorts` profile (W17) |
| `broll_only` | Burn only over storyboard clips where `renderer === "broll"` |
| `always` | Burn over full episode timeline (legacy Shorts convention) |

Optional per-clip override on compose `clip_ref`: `"captions": false` suppresses
burn-in for that clip's `[offset_s, offset_s+duration]` even when policy would
allow it (subtractive only — cannot force burn-in when episode policy is `never`).

## Allowlist
composition/captions.py · tools/align_vo.py · tests/test_captions.py (new) ·
requirements.txt (whisperX/stable-ts dependency line only)

## Stub + contract notes (this lane — not W02)

W02 already shipped a minimal `composition/captions.build(...)` stub. **This
lane extends it** — add `burn_windows: list[tuple[float, float]] | None = None`
and sidecar output; do not revisit W02.

Frozen schema changes are **lead-owned** (out of every lane allowlist). At
integration the lead adds to `docs/contracts/`:

| Schema | Fields |
|---|---|
| `compose.schema.json` | `caption_policy { burn_in, sidecar }`; optional `clip_ref.captions`, `clip_ref.renderer` |
| `episode.schema.json` | optional top-level `caption_policy`; optional `storyboard_entry.captions` |

Develop and test `burn_windows` via unit tests and inline compose dicts; W17
wires the spec → `burn_windows` call. Fixture shape: see W17 T3.


### T1 — Alignment tool
`tools/align_vo.py <vo.wav> [--script beats.txt]` → `<vo>.words.json`:
`[{word, start, end, confidence}]`. Use whisperX (preferred) or stable-ts —
pick one, justify in a comment, pin the version. If a script text is
provided, align against it (fewer ASR errors) rather than transcribing.
CPU must work (slow is fine); CUDA used when available (3070 Ti local).

### T2 — Chunker
words.json → caption chunks: 1–3 words, break on punctuation/clause
boundaries, never split a number from its unit, min display
`callout_min_s`-derived floor (timing tokens), merge ultra-short gaps.
Emphasis: words wrapped `**like this**` in the script text carry
`emphasis: true` through to styling.

### T3 — ASS generator
Chunks → ASS file styled from tokens. This is a **brand-minimal transcript
strip** — NOT Manim callout styles (neon/glass/leader), NOT map label/stat-
box styles. Purpose: readable VO mirror for clips without an authored text
layer (chiefly b-roll); short-form 1–3-word cadence, static (no entrance anim).

Styling from tokens: `typography.primary` (Inter), sizes from
`typography.scale[format].caption` × a caption multiplier, white text /
`background`-toned 70% opacity backing box OR outline (pick the cleaner on
the dark brand background — show both in report), emphasis words tinted
`roles.highlight.core`. Position: default = center of
`safe_areas[format].caption_band`.

### T4 — Occupancy-aware placement
Input: the composed timeline's layout.json files + per-clip start offsets
(from compose.schema fixture). For each chunk, evaluate candidate positions:
(1) default caption band, (2) upper-third band mirrored from tokens,
(3) mid-low fallback; score = overlap area with layout boxes during the
chunk's interval (weight callout-kind boxes 3×); pick min-score with
hysteresis (stay put unless current score exceeds threshold AND alternative
is ≥2× better — no caption jitter). Hard rule: never inside
platform_margins. Implements `captions.build(...)` (see signature below).

`build(..., burn_windows=None)` — when `burn_windows` is a list of
`[start_s, end_s]` intervals (episode time), emit ASS dialogue lines **only**
for chunks whose `[start, end]` overlaps a burn window; all other chunks are
omitted from the ASS (still included in `.srt` when sidecar is requested).
`burn_windows=None` means burn the full aligned timeline (equivalent to
`burn_in: always`). W17 computes windows from `caption_policy` + per-clip
`captions` overrides.

### T5 — Outputs
- Burn-in path: return the ASS path for engine's ffmpeg `subtitles=` filter
  (engine wiring is W17's; just ensure the file + a tiny standalone
  `ffmpeg` burn command in the docstring works). Skip ASS generation entirely
  when policy `burn_in` is `never` (sidecar-only route).
- Sidecar path: also emit `.srt` (plain, no styling) for YouTube CC upload
  when `caption_policy.sidecar` is true — full VO transcript regardless of
  burn windows.

### T6 — Tests + demo
test_captions.py: chunker rules (golden cases incl. numbers, punctuation,
emphasis), placement scoring against a crafted layout fixture where the
default band is occupied (must relocate), hysteresis (oscillating occupancy
must not flip-flop), **burn_windows** filtering (chunks outside windows
absent from ASS but present in SRT). Demo: any short wav (record/use TTS
sample committed to tests/fixtures/) → burned-in 9:16 test clip over a
solid-color video simulating a b-roll window, screenshot in report.

## Out of scope
engine.py / sound.py / export.py · renderer changes · VO generation.

## Acceptance
`pytest tests/test_captions.py` green; demo clip renders with visibly
brand-styled captions; relocation demonstrably triggers on the occupied
fixture (two screenshots: default vs relocated).

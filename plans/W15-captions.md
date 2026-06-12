# W15 — Captions: forced alignment → styled ASS → occupancy-aware burn-in

Branch: `agents/w15-captions` · Depends on: W02 (contracts + tokens +
composition stubs). Integrates with real layout.json after W10/W13 merge —
develop against `docs/contracts/fixtures/`.

## Goal
Word-level captions from VO audio: 1–3 word chunks, brand-styled, occupancy-
aware placement that never covers content, burn-in for vertical, sidecar CC
for long-form. Captions are TRANSCRIPT; callouts are COMPRESSION — captions
never replace or duplicate the callout role.

## Allowlist
composition/captions.py · tools/align_vo.py · tests/test_captions.py (new) ·
requirements.txt (whisperX/stable-ts dependency line only)

## Checklist

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
Chunks → ASS file styled from tokens: `typography.primary` (Inter), sizes
from `typography.scale[format].caption` × a caption multiplier, white text /
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
platform_margins. Implements `captions.build(...)` signature from the stub.

### T5 — Outputs
- Burn-in path: return the ASS path for engine's ffmpeg `subtitles=` filter
  (engine wiring is W17's; just ensure the file + a tiny standalone
  `ffmpeg` burn command in the docstring works).
- Sidecar path: also emit `.srt` (plain, no styling) for YouTube CC upload.

### T6 — Tests + demo
test_captions.py: chunker rules (golden cases incl. numbers, punctuation,
emphasis), placement scoring against a crafted layout fixture where the
default band is occupied (must relocate), hysteresis (oscillating occupancy
must not flip-flop). Demo: any short wav (record/use TTS sample committed to
tests/fixtures/) → burned-in 9:16 test clip over a solid-color video,
screenshot in report.

## Out of scope
engine.py / sound.py / export.py · renderer changes · VO generation.

## Acceptance
`pytest tests/test_captions.py` green; demo clip renders with visibly
brand-styled captions; relocation demonstrably triggers on the occupied
fixture (two screenshots: default vs relocated).

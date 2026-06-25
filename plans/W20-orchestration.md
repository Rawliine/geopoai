# W20 — Orchestration: episode manifest, stage runner, QC, publish — NO LLM API

Branch: `agents/w20-orchestration` · Depends on: Wave 1 merged (esp. W17).

## Goal
The episode factory as a staged state machine over one persistent artifact
(`episodes/<id>/episode.json`, schema: docs/contracts/episode.schema.json).
**Constraint: zero LLM API calls.** Every authoring stage ("brain stage")
halts with a written instruction + schema; Claude Code (the operator's
session) authors the artifact; `validate` checks and advances. The brain
interface must be swappable for API calls later without touching stages.

## Allowlist
orchestration/ (new package) · pipeline/orchestrate.py (new) ·
config/show_bible.geopoai.json (new) · tests/test_orchestration.py (new)

## Read first
docs/contracts/*.schema.json (all) · pipeline/render.py · pipeline/compose.py ·
pipeline/broll.py (exit codes, --ask/--pick) · plans/PLAN.md (goal section)

## Checklist

### T1 — Manifest + runner
`orchestration/manifest.py`: load/save/validate episode.json, stage status
transitions (pending → awaiting_brain | running → done | failed), artifact
hash recording. Optional top-level **`caption_policy`** on the manifest
(inherits bible default when absent; operator sets before `script`). 
`orchestration/runner.py`: stage registry, sequential
`next`, idempotent re-runs. CLI `pipeline/orchestrate.py`:
`new <show> <episode_id>` · `status` · `next` · `validate <stage>` ·
`run <stage>` · `qc` · `invalidate <stage|clip_id>`.
Also `orchestration/README.md`: stage map, the brain protocol (next →
author artifact → validate), manifest lifecycle — this layer's SKILL.md
equivalent.

### T2 — Show bible
`config/show_bible.geopoai.json`: show_id; positioning statement ("show the
incentives"); hook grammar — list of schema+twist hook patterns, each
`{ name, familiar_schema, broken_variable, example }`; beat templates
(hook / context / incentive-model / resolution / implication); tone
("analytical, dry wit allowed in callouts"); component palette preferences;
default formats; topic source notes; validator thresholds (override
tokens.timing where needed); per-platform metadata rules; **`caption_policy`**
default `{ "burn_in": "broll_only", "sidecar": true }` — operator may
override per episode in `episode.json` before brain stages run.
`orchestration/bible.py` loader. Stages read EVERYTHING genre-flavored from
the bible — zero geopolitics hardcoded in orchestration/ (test enforces:
grep stages/ for "geopoli" must hit nothing).

### T3 — Stages (orchestration/stages/*.py)
- `ingest`: inputs = URLs, local files, pasted notes. URLs fetched
  (readability text extraction; media via broll reference ingest for
  video/images). Output: evidence.json — quotes/stats/claims/media refs,
  each with source + retrieved_at. Brainless (mechanical).
- `angle` (BRAIN): instruction asks for: chosen angle, the incentive
  structure (actors/options/payoffs sketch), the hook (per bible hook
  grammar — familiar_schema + broken_variable explicit fields). Schema-
  validated artifact angle.json.
- `script` (BRAIN): VO script as beats[]: { beat_id, vo_text (with **emphasis**
  markup), intent, evidence_refs[] }. Instruction includes the episode's
  **`caption_policy`**: VO is the full transcript; on-screen text in scenes
  is compression only (callouts/labels) — do not duplicate VO verbatim in
  scene JSON. Validator: every factual beat carries ≥1 evidence_ref; reading
  time vs target duration check.
- `storyboard` (BRAIN): beat → clips: renderer (map|manim|broll|escape_hatch),
  duration, scene-file path to author next, format targets. Optional
  `"captions": false` on a row to suppress burn-in for that clip (subtractive
  override). Validator: durations sum ≈ VO; renderer exists; max consecutive
  same-renderer (bible threshold).
- `scenes` (BRAIN): per-clip scene JSONs / shot specs authored into
  episodes/<id>/scenes/; validate each against its renderer schema
  (manim validator, map schema, shot spec schema).
- `voice` (placeholder): expects episodes/<id>/vo.wav supplied externally
  (S2-pro later); stage just verifies presence + duration vs script estimate.
- `render`: dispatch each clip through pipeline/render.py — PARALLEL
  (process pool, configurable width), content-hash skip: scene file hash +
  renderer version recorded in manifest; only dirty clips re-render.
  Broll --ask checkpoints surface as awaiting_brain with the contact sheet
  path in the instruction.
- `compose`: build compose spec from storyboard (transitions: bible default
  whoosh on camera-adjacent boundaries, else cut); copy episode `caption_policy`
  into spec; set per-clip `renderer` + optional `captions` on each `clip_ref`
  → pipeline/compose.py.
- `qc`: see T4. - `publish`: see T5.

### T4 — QC stage
Machine checks, report to episodes/<id>/qc_report.md, failures block:
- callout-duplication: for each manim callout (scene JSONs) overlapping VO
  interval (words.json), token-overlap ratio vs concurrent VO sentence
  > 0.6 → fail ("callouts compress, never transcribe");
- pacing: aggregate events.json — gaps > static_max_s, density spikes;
- caption collisions: when burn-in is active, ASS positions vs layout.json
  overlap report (skip when `burn_in: never`);
- loudness: final mix −14±1 LUFS; clip/format integrity (every storyboard
  clip present, right resolution).

### T5 — Publish stage (BRAIN, metadata only — no uploads)
Instruction asks for per-platform titles/descriptions/tags + thumbnail
brief; validator checks platform character limits from the bible.

### T6 — Iteration ("edit one scene, keep everything")
`invalidate <clip_id>` marks one clip dirty → `run render` re-renders only
it → `run compose`/`qc` re-run cheaply. Same for `invalidate script`
(downstream stages flip to pending; untouched-clip hashes still skip
re-render where storyboard rows are unchanged). Test proves: 3-clip episode,
edit 1 scene file, exactly 1 re-render occurs.

### T7 — Tests + dry episode
Mocked-renderer tests for runner/hash/invalidate/QC rules. Committed
`episodes/_example/` dry episode with hand-authored brain artifacts
exercising every stage to `compose` with stub clips.

## Out of scope
LLM API integration (interface only) · uploads · TTS · new renderer features.

## Acceptance
`orchestrate.py new geopoai ep000 && next` walks the full stage sequence on
the example episode; T6 selective re-render test green; QC report generated
with at least one deliberately-failing fixture demonstrating each rule;
pytest green.

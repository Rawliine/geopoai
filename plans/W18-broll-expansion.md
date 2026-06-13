# W18 — B-roll: env audit, public-domain news sources, link ingest, prompt eval

Branch: `agents/w18-broll` · Depends on: W02.

## Allowlist
broll/ · pipeline/broll.py · .env.example (new) · tests/test_broll_*.py

## Read first
broll/recap.md (cascade rationale) · broll/lib/cascade.py · sources/_base.py ·
sources/wikimedia.py (reference implementation) · lib/verify.py ·
lib/vision_verifier.py · broll/schema/shot_spec_schema.json

## Checklist

### T1 — Env audit + .env.example
Grep every `getenv/environ` across broll/ (and lib/vision_verifier.py
specifically). Write `.env.example` documenting every variable with one
comment line each (placeholder values). Report the definitive missing-keys
list (expected: PIXABAY_API_KEY, ANTHROPIC_API_KEY; verify NARA/LoC needs).
Make missing-key behavior uniform: source skipped with a logged reason
(cascade.walk already converts auth errors — verify pixabay/pexels do this).

### T2 — DVIDS source
`sources/dvids.py`: DVIDS public API (US military footage, public domain) —
search by keywords, video assets only, license/provenance into the wrapper
like wikimedia.py does. Slot into cascade order after NARA. Respect
rate_limit.py.

### T3 — NASA source
`sources/nasa.py`: NASA Image and Video Library API (images-api.nasa.gov,
no key) — video assets, PD provenance. Cascade after DVIDS. (Earth-from-
space / launch / satellite footage — recurring needs for this genre.)

### T4 — Reference ingest (user-supplied links)
`sources/reference.py` + shot spec extension `reference_urls: [..]`:
- Fetcher: yt-dlp (handles YouTube/TikTok/IG/X/news embeds via generic
  extractor; pin version); fallback: page fetch → og:video / `<video>` /
  largest images.
- Provenance: `license: "user_provided"`, source_url, retrieved_at — through
  asset_wrapper like every asset. Cache by URL hash under
  data/.cache/broll/refs/.
- Segment selection: PySceneDetect split → CLIP prefilter ranks segments
  against the shot intent (reuse lib/clip_prefilter.py) → vision verifier
  confirms top segment → trim to duration_seconds with ffmpeg.
- Checkpoint mode (`--ask`): instead of auto-trim, write a contact sheet
  (thumbnail grid PNG with timestamps) + candidates.json next to the shot
  output and exit with a distinct code; a follow-up run with
  `--pick <segment_id>` completes the shot. (W20 surfaces this checkpoint.)
- Routing: when `reference_urls` present, reference source runs FIRST,
  before the stock cascade; decision matrix otherwise unchanged.

### T5 — Prompt-adherence eval harness
`broll/tools/eval_prompts.py` + `broll/tests/fixtures/eval_bank.json`:
10 fixed shot intents spanning kinds (conceptual/establishing/atmospheric/
face-bearing). For each: generate via the AI path (requires live ComfyUI —
`--require-comfyui` flag, otherwise dry-run printing assembled prompts),
score with vision_verifier, emit a markdown scoreboard comparing prompt
template versions (template version string already in provenance meta —
verify, else add). Purpose: re-run on every prompt-template or model change.

### T6 — Tests
Mocked-HTTP tests for dvids/nasa/reference (no live network), contact-sheet
generation, routing precedence.

### T7 — Docs fragment
`broll/docs/fragments/W18.md`: reference_urls usage (--ask/--pick flow,
contact sheet), the new sources and their cascade positions, eval harness
usage, the full env-var table.

## Out of scope
ComfyUI workflows · infra · orchestration (only the exit-code contract).

## Acceptance
pytest green; `python pipeline/broll.py <fixture with reference_urls>
--ask` produces a contact sheet from a local fixture video (commit a tiny
test mp4); `--pick` completes with valid .meta.json; eval harness dry-run
prints 10 assembled prompts; .env.example complete.

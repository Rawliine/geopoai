# W27 — B-roll provided media: operator/LLM-supplied clip as a forced source

Branch: `agents/w27-broll-provided-media` · Depends on: W18 (broll live, merged) —
runs in parallel with W24/W25/W26.

## Goal
Let a **supplied media URL or local file** (from an episode `broll` input) be used
directly as a b-roll clip — a "provided source" that **short-circuits keyword
sourcing** (a forced pick) while still carrying mandatory provenance/license metadata
and flowing through the normal clip/eval path. This is how an input video link becomes
a cutaway clip in the timeline.

## Allowlist
`broll/lib/provided_source.py` (new) · `pipeline/broll.py` (add a `--provided`
entry / shot field) · `broll/docs/fragments/w27-provided-media.md` (new) ·
`tests/test_broll_provided.py` (new)

## Read first
`broll/lib/asset_wrapper.py` (mandatory license fields — mirror its provenance
discipline) · `broll/lib/decision.py` + `broll/lib/ai_router.py` (selection/eval
flow to short-circuit) · `pipeline/broll.py` (exit codes, `--ask`/`--pick`) ·
`broll/AGENT.md` · `assets/manifest.json` rules (no ad-hoc downloads)

## Checklist

### T1 — Provided-source module
`provided_source.py`: accept `{ url | path }`; fetch/validate the media (reuse the
existing broll downloader/asset wrapper — **no new dep**), probe duration/dims, and
wrap it as a candidate with `source="provided"`, `license` (required; operator/LLM
supplies attribution), and `retrieved_at`. Reject if license missing.

### T2 — Short-circuit into selection
A provided candidate bypasses keyword search + ranking (forced pick) but still passes
the integrity/verifier gate (or an explicit `--trust-provided` skip), so a known-good
clip is used as-is while a junk file is still caught.

### T3 — CLI/shot wiring
`pipeline/broll.py`: `--provided <url|path>` (and a `provided` field on a shot spec)
that routes to T1→T2; exit-code/`--ask` behavior consistent with sourced shots.

### T4 — Tests + fragment
Provided URL and local file each become a usable clip with license metadata; missing
license raises; junk file is rejected at the gate. `docs/fragments/w27-provided-media.md`
documents the input field + flag.

## Out of scope
Orchestration / `inputs[]` routing (W20 maps `use:"broll"` → this) · new renderers ·
map/manim media (W25/W26) · changing the sourcing cascade for non-provided shots.

## Acceptance
A provided URL **and** a provided local file each yield a b-roll clip with required
license metadata and correct duration; missing-license + junk-file cases rejected;
`pytest tests/test_broll_provided.py` green.

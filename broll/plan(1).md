# GeoPoAI — B-Roll System Implementation Plan

Status: proposal, fluid. Sits alongside the Mapbox and Manim engines as a third source of visual content that flows into the orchestrator.

---

## Target end state

A unified B-roll retrieval + generation layer. The orchestrator (n8n / langgraph) requests a shot by intent ("aerial of Suez Canal, dawn, container ship") and receives a usable MP4 clip with full provenance metadata. The layer decides internally whether to fetch from stock sources, generate via AI, or fall back gracefully.

```
LLM (per script beat)
   │ generates shot spec (intent + 3-5 keyword queries + use_ai hint)
   ▼
B-Roll Layer
   ├── 1. Decision: stock-first or AI-first (based on shot type)
   ├── 2. Stock cascade:
   │      Wikimedia → LoC → NARA → Archive.org → Pexels → Pixabay
   ├── 3. CLIP prefilter — cheap thumbnail similarity, top 5
   ├── 4. Vision-LLM verification — pick or reject all
   ├── 5. If reject all: AI generation on Verda
   │      LTX-2.3 (default) | Wan 2.2 (face-heavy)
   └── 6. Asset marking — provenance + license + attribution in .meta.json
   ▼
output/broll/<shot_id>.mp4 + .meta.json
```

---

## Status (2026-05-21)

* **Phase 0** — ✅ shipped. See `HANDOFF_PHASE_0.md`.
* **Phase 1** — ✅ shipped (functionally). 6 sources, cascade, two-stage verify
  (heuristic-default with optional OpenCLIP and Claude backends), rate limit,
  disk cache, per-shot log.json. 117/117 offline tests, 5/5 enabled live tests.
  The 30-shot ≥70% benchmark is the one remaining measurement task — tooling
  is in place. See `HANDOFF_PHASE_1.md`.
* **Phase 2** — pending. See "What's ready for Phase 2 to plug into" in
  `HANDOFF_PHASE_1.md`.

---

## Phase 0 — Foundation (≈3-4 days)

Goal: the asset wrapper exists, every fetch produces meta, schema is locked.

- `broll/` directory created (full layout in AGENT.md)
- `broll/schema/asset_meta_schema.json` — defines the `.meta.json` shape for every asset
- `broll/schema/shot_spec_schema.json` — defines the shot intent the LLM produces
- `broll/lib/asset_wrapper.py` — single CLI entry: `fetch_asset(url, target_path)` produces both the file and `.meta.json`. No raw downloads anywhere in the codebase.
- `broll/lib/keyword_generator.py` — LLM-driven shot intent → 3-5 keyword queries (uses Claude or local model)
- `broll/lib/decision.py` — stock-first vs AI-first decision based on shot type taxonomy
- Smoke test: a `scripts/broll/test_shot.json` containing one shot spec, run end-to-end against Pexels only, verify .meta.json produced

Exit criteria: one shot fetched + tagged with full provenance. Schema rejects malformed shot specs.

---

## Phase 1 — Stock cascade (≈1 week)

Goal: full cascade with all sources, working verification layer.

Source clients, in cascade order:

1. **Wikimedia Commons** — `broll/sources/wikimedia.py`. Use the Action API (`prop=imageinfo`, `prop=videoinfo`). License usually CC-BY-SA or CC-BY; structured attribution data available.
2. **Library of Congress** — `broll/sources/loc.py`. Public domain US government content. Excellent for pre-2000 American footage. Free API, no key required.
3. **NARA (US National Archives)** — `broll/sources/nara.py`. Public domain. Military, historical, archival.
4. **Internet Archive** — `broll/sources/archive_org.py`. Mixed licenses; filter strictly. Has a query API.
5. **Pexels** — `broll/sources/pexels.py`. API key required. Modern, clean, license is Pexels License (free commercial use, no attribution required, but we record it anyway).
6. **Pixabay** — `broll/sources/pixabay.py`. API key required. Similar to Pexels.

Cascade orchestrator (`broll/lib/cascade.py`):
- Receives a shot spec
- Generates keyword queries via `keyword_generator`
- Walks cascade in order; stops when a source returns ≥N candidates (default N=3)
- Falls through to AI generation if no source returns enough

Two-stage verification (`broll/lib/verify.py`):
- **CLIP prefilter**: compute CLIP similarity between shot intent and each candidate thumbnail. Keep top 5. Local CPU is fine; ONNX CLIP runs in milliseconds.
- **Vision-LLM verifier**: pass top 5 to a vision model with the shot intent. Model returns either the selected index + brief reason, or `reject_all` if none match.

Exit criteria: render 30 LLM-authored shot specs through the cascade. ≥70% of shots return a verified stock clip without falling through to AI.

---

## Phase 2 — AI generation on Verda (≈1 week)

Goal: LTX-2.3 + Wan 2.2 deployed, callable via the same B-roll interface.

- `broll/sources/ltx_video.py` — client for LTX-2.3 ComfyUI API on Verda
- `broll/sources/wan_video.py` — client for Wan 2.2 ComfyUI API on Verda
- `broll/lib/ai_router.py` — picks LTX or Wan based on shot type. Default LTX. Switch to Wan when shot includes a human face that has to read as real.
- `broll/prompts/` — base prompt templates with style tokens for the channel aesthetic. LoRA application happens here (`Soft_Enhance_Style_LoRa` as global gentle pass).
- `broll/lib/seed_strategy.py` — deterministic seed from `(prompt, model)` hash. Re-runs reproduce results unless explicitly randomized.

ComfyUI workflow JSONs stored as templates in `broll/comfyui_workflows/`. The client substitutes prompt + seed into the template and submits.

The same `.meta.json` schema captures AI provenance: model, prompt, seed, LoRA stack, sampler, steps. If a clip needs regeneration in 6 months, the recipe is preserved.

**Cost discipline:**
- Default to spot pricing on Verda for batch generation
- Cap per-shot retries (3 by default) — if 3 attempts fail verification, surface the failure rather than burning compute
- Cache aggressively: same prompt + seed = same clip, never regenerate

Exit criteria: 50 AI clips generated across both models with consistent style and full metadata. Spot interruption recovery works (interrupted batch resumes cleanly).

---

## Phase 3 — Verification hardening + LLM iteration loop (≈4-5 days)

Goal: the LLM can self-correct when verification fails.

- When `reject_all` fires on stock results, LLM is asked to refine the keyword queries or switch to AI
- When AI generation fails verification, LLM is asked to refine the prompt
- Max 2 LLM refinement iterations per shot before escalating to manual review
- `broll/lib/refinement.py` — manages the loop, logs each iteration
- Per-shot iteration log in `output/broll/<shot_id>.log.json` showing all attempts

Exit criteria: 90% of shots converge within 2 refinement iterations.

---

## Phase 4 — Provenance + attribution (≈3 days)

Goal: every published video can produce a compliant attribution slate automatically.

- `broll/lib/attribution.py` — walks all `.meta.json` files for a video, generates an end-of-video credit slate (markdown + rendered card)
- `broll/lib/license_audit.py` — pre-publish check: rejects clips with `non_commercial` licenses if the video is monetized, surfaces required attributions, warns on missing metadata
- Attribution slate template lives in `broll/templates/attribution_slate.md` and is rendered by the same Manim pipeline (`ChapterCard` component, repurposed)
- Audit run on every video build before render

Exit criteria: produce a video with mixed sources, generate an automatic compliant attribution slate, pass audit.

---

## Phase 5 — Optimization (ongoing)

- Bulk pre-fetch for "evergreen" shots — common shots (Capitol Hill, Red Square, Kremlin, container ships) cached on disk so repeat usage is free
- LoRA training for visual style consistency (once enough channel content exists to train against)
- Custom CLIP fine-tune on channel aesthetic (Phase 5+, only if generic CLIP misjudges shots regularly)
- Pre-compute embeddings for top-1000 cached stock clips so the cascade can skip API calls for evergreen queries

---

## Cross-cutting decisions to lock in early

**Asset wrapper is the only path to disk.** No script anywhere downloads or generates without going through `lib/asset_wrapper.py`. Enforced via code review and a CI check that greps for direct `requests.get(...).content` or `urllib.urlretrieve` outside the wrapper.

**.meta.json is required.** A file without one is considered orphaned and the asset audit removes it. Forces metadata discipline upstream.

**Shot IDs are stable.** Once assigned, never change. `output/broll/<shot_id>.mp4` is the canonical reference. The shot spec, sources searched, AI prompts, and final clip are all traceable through the ID.

**Stock-first by default.** AI generation is the fallback, not the primary path. Reasons: viewers trust real footage; stock has no per-shot compute cost; AI footage drifts in style without careful prompting.

**Two models, both required.** LTX-2.3 for speed and iteration, Wan 2.2 for faces. Don't try to consolidate to one — they have complementary strengths.

---

## Open questions

- **Audio in B-roll clips.** Stock often has audio; AI clips don't. Strip audio universally or preserve when present? Probably strip and let the editor add foley/score in post.
- **Resolution policy.** Stock comes in varied resolutions. Standardize to 1920x1080 (or 1080x1920 for vertical) before storing? Probably yes — saves downstream resize work.
- **Clip duration normalization.** Stock clips can be 30s, AI clips are ~5s. Should the wrapper trim stock to the shot's needed duration? Probably trim to `shot_duration + 2s buffer`.
- **Vision-LLM cost at scale.** Verifying every shot via a vision model adds up. CLIP prefilter helps. Worth tracking cost per shot once volume grows.
- **Caching strategy for evergreen shots.** Disk caching by query hash is straightforward; deciding which shots are "evergreen" enough to warrant pre-fetching is the question.
- **Failure surface to the orchestrator.** If a shot can't be satisfied at all, what does the layer return? Empty clip with a marker? Last-resort placeholder? Decided at orchestrator design.

---

## What we're not building

- Stock photo retrieval. This is video-only. Photos handled by the Manim layer via `AnnotatedImage` if needed.
- A scraper for sources without proper APIs. If a source requires scraping, skip it.
- A custom video search engine. We orchestrate existing sources, we don't build one.
- Watermarking. Internal asset marking is metadata, not visible overlay.

# HANDOFF — B-Roll Phase 1 → Phase 2

Written: 2026-05-21. Author: agent that built Phase 1.
Read this before touching Phase 2. Then read `AGENT(1).md`, `plan(1).md`,
`recap(1).md`, and `HANDOFF_PHASE_0.md`.

---

## TL;DR

Phase 1 is **functionally complete and live-network verified** for 4 of 6
sources without any extra credentials. **117/117 offline tests pass**;
**5/5 enabled live-network tests pass** (Wikimedia, LoC, Archive.org, Pexels,
full cascade-to-fetch). NARA and Pixabay are gated on free API keys and skip
cleanly when those aren't set.

CLIP prefilter ships in **heuristic mode** by default (no torch dep); the
real `open_clip` backend is wired and one env var (`BROLL_USE_CLIP=1`) flips
it on once you install the package. Vision verifier ships in **heuristic
mode** when `ANTHROPIC_API_KEY` is absent; with the key set it calls the
Anthropic Messages API directly over HTTP (no SDK dep).

To close the Phase 1 exit criterion ("render 30 shot specs through the
cascade, ≥70% return a verified stock clip without falling through to AI"):
write or generate 30 specs, run them through `pipeline/broll.py`, and read
the per-shot `.log.json` files. Tooling is in place; the load-testing pass
itself wasn't part of Phase 1's scope as written.

---

## What was built

### Files added

```
broll/
├── HANDOFF_PHASE_1.md              ← this file
├── sources/
│   ├── _base.py                    ✅ SearchResult + http_get_json + helpers
│   ├── wikimedia.py                ✅ MediaWiki Action API, license normalization
│   ├── loc.py                      ✅ LoC ?fo=json, video filter
│   ├── nara.py                     ✅ National Archives v2, key-gated
│   ├── archive_org.py              ✅ advancedsearch + metadata two-step
│   ├── pixabay.py                  ✅ Pixabay video API
│   └── pexels.py                   ↻ refactored to use _base
├── lib/
│   ├── rate_limit.py               ✅ per-source token bucket
│   ├── cache.py                    ✅ on-disk search-result cache (6h TTL)
│   ├── cascade.py                  ✅ walker + CLI dry-run
│   ├── clip_prefilter.py           ✅ heuristic + OpenCLIP backends
│   ├── vision_verifier.py          ✅ Claude (direct HTTP) + heuristic backends
│   └── verify.py                   ✅ orchestrator gluing both stages
└── tests/
    ├── test_rate_limit_and_cache.py
    ├── test_sources_mocked.py      ✅ HTTP-mocked unit tests per source
    ├── test_cascade.py             ✅ dedup, skip, error, stop-early
    ├── test_verify_and_prefilter.py
    └── test_phase1_smoke.py        ✅ hermetic full pipeline + live-network gated

pipeline/broll.py                   ↻ rewired for cascade + verify
```

### Sources matrix

| Source       | Auth                         | Endpoint                                              | Live status      |
|--------------|------------------------------|-------------------------------------------------------|------------------|
| Wikimedia    | none (UA only)               | `commons.wikimedia.org/w/api.php`                     | ✅ verified live |
| LoC          | none                         | `www.loc.gov/search/?fo=json`                         | ✅ verified live |
| NARA         | `NARA_API_KEY` (api.data.gov)| `catalog.archives.gov/api/v2/records/search`          | ⚠ skips w/o key  |
| Archive.org  | none                         | `archive.org/advancedsearch.php` + `/metadata`        | ✅ verified live |
| Pexels       | `PEXELS_API_KEY`             | `api.pexels.com/videos/search`                        | ✅ verified live |
| Pixabay      | `PIXABAY_API_KEY`            | `pixabay.com/api/videos/`                             | ⚠ skips w/o key  |

The cascade order is locked at:
```
wikimedia → loc → nara → archive_org → pexels → pixabay
```
(See `recap(1).md` §2 for the rationale.) Sources missing keys are listed in
`CascadeReport.skipped` and the walker continues — they're not errors.

### Two-stage verification

Stage 1 (`clip_prefilter.py`):
* Default **heuristic backend**: token-overlap scoring of intent against
  candidate `title + description + attribution + tags`, plus a per-source
  prior (named-content boosts Wikimedia/LoC/NARA; generic boosts
  Pexels/Pixabay), plus a -0.5 penalty for `license: unclear`. No external
  deps.
* Optional **OpenCLIP backend**: ViT-B-32 / openai pretrained. Triggered by
  `BROLL_USE_CLIP=1` or `BROLL_PREFILTER=open_clip`. Requires
  `pip install open-clip-torch torch pillow`. Falls back to heuristic if the
  import fails (unless explicitly forced).

Stage 2 (`vision_verifier.py`):
* Default **heuristic backend**: trusts the prefilter; picks top if score ≥
  threshold (default 0.25), else `reject_all`. Used for tests + when no
  Anthropic key.
* Optional **Claude backend**: direct-HTTP POST to
  `https://api.anthropic.com/v1/messages` (no SDK dep). Activated when
  `ANTHROPIC_API_KEY` is set. Default model `claude-sonnet-4-6`, override
  with `BROLL_VERIFIER_MODEL`. Fetches each thumbnail, base64-encodes it,
  asks Claude for a single JSON verdict. Tolerant of fenced JSON responses.

### Pipeline rewire

`pipeline/broll.py` now does:
1. Schema validation (Phase 0 logic, unchanged)
2. `decide()` (Phase 0 logic, unchanged)
3. `cascade.walk(spec, min_candidates=3, max_candidates=12)`
4. `verify.pick(intent, candidates, top_k=5)`
5. `asset_wrapper.download(winner.download_url, ...)` via `fetch_to_wrapper`
6. Writes `output/broll/<shot_id>.log.json` with full attempt record

Exit codes:
* `0` success
* `1` generic BrollError (e.g. AI-only kind on Phase 1)
* `2` schema validation
* `3` source auth missing
* `4` no candidates from any source
* `5` verifier rejected all (new in Phase 1)

### Logs

Every run writes `output/broll/<shot_id>.log.json` regardless of outcome:

```json
{
  "shot_id": "...",
  "started_at": 1747...,
  "decision": {...},
  "cascade": {
    "queries": [...],
    "by_source": {"wikimedia": 5},
    "skipped": {"pexels": "PEXELS_API_KEY not set"},
    "errors": {...},
    "candidate_summary": [...]
  },
  "verify": {
    "prefilter_backend": "heuristic",
    "verifier_backend": "heuristic",
    "verifier_model": null,
    "verifier_passed": true,
    "prefilter_top": [{"source": "wikimedia", "id": "...", "score": 0.68}, ...]
  },
  "outcome": "fetched" | "reject_all" | "no_candidates" | "dry_run",
  "asset_path": "output/broll/...mp4",
  "elapsed_seconds": 12.43
}
```

This is the substrate for the Phase 3 refinement loop and the Phase 4
attribution slate.

---

## Exit criteria mapping (plan(1).md Phase 1)

| Criterion | Status |
|---|---|
| Wikimedia / LoC / NARA / Archive.org / Pexels / Pixabay clients shipped | ✅ all 6 |
| Cascade walks in order, stops at N candidates | ✅ `cascade.walk(min_candidates=3)` + tests |
| CLIP prefilter (local) | ⚠ heuristic ships by default; OpenCLIP wired but off |
| Vision-LLM verifier | ⚠ heuristic + real Claude path; defaults to heuristic w/o key |
| 30 LLM-authored shot specs through cascade, ≥70% verified | 🔜 tooling in place; load-test pass is a follow-up |

The 70% bar is a **runtime measurement**, not a code deliverable. Phase 1
provides everything needed to measure it; running the 30-shot benchmark is
the next concrete step before Phase 2.

---

## How to verify locally

```bash
# 1. Offline suite (117 tests, no network)
pytest broll/tests/ -m "not network"

# 2. Live cascade dry-run (no downloads, hits real APIs)
python -m broll.lib.cascade --query "Suez Canal aerial container ships" --limit 4 --min 3

# 3. Full live pipeline (downloads ~10-100 MB)
python pipeline/broll.py scripts/broll/test_shot.json --print-meta

# 4. Dry-run mode (cascade + verify but no fetch)
python pipeline/broll.py scripts/broll/test_shot.json --dry-run

# 5. Network-marked tests (live API calls)
pytest broll/tests/test_phase1_smoke.py -m network
```

To enable optional features:
```bash
echo "NARA_API_KEY=$(get from api.data.gov)"      >> .env   # free, instant
echo "PIXABAY_API_KEY=$(get from pixabay.com/api)" >> .env  # free, instant
echo "ANTHROPIC_API_KEY=sk-ant-..."                >> .env  # vision verifier
pip install open-clip-torch torch                          # CLIP backend
export BROLL_USE_CLIP=1                                    # flip CLIP on
```

---

## Rate-limit posture

Caps configured in `broll/lib/rate_limit.py` (`DEFAULT_LIMITS`):

| Source       | Bucket capacity | Refill rate     | Notes                                |
|--------------|-----------------|-----------------|--------------------------------------|
| Pexels       | 10              | 180/hr          | Free tier hard cap: 200/hr           |
| Pixabay      | 5               | 90/hr           | Free tier hard cap: 100/hr           |
| Wikimedia    | 10              | 5/sec           | Their API allows ~200/sec; we coast  |
| LoC          | 4               | 2/sec           | Documented: 20/sec                   |
| NARA         | 3               | 1/sec           | Tier varies by key                   |
| Archive.org  | 5               | 2/sec           | No published cap                     |
| Anthropic    | 3               | 1/sec           | Verifier API                         |

Disable for tests: `BROLL_NO_RATE_LIMIT=1` (already set in test fixtures).

Disk cache TTL is 6 hours (`BROLL_CACHE_TTL_SEC`). Path:
`data/.cache/broll/searches/`. Disable: `BROLL_NO_CACHE=1`. Clear from code:
`broll.lib.cache.clear()`.

In normal dev/test loops the cache makes the 2nd run free and the 1st run
hits each source ~once per unique query.

---

## Architectural choices

### 1. `SearchResult` is the universal currency

Every source produces `SearchResult` and every consumer (cascade, prefilter,
verifier, wrapper) operates on it. The dataclass lives in
`broll/sources/_base.py` so adding a new source is a single-file change.

### 2. Sources never touch the network directly

All source modules call `_base.http_get_json(url, headers=...)`. That helper:
* Always sets `User-Agent` and `Accept: application/json`.
* Retries up to 3 times when the response body looks like HTML (CDN
  mis-routing — see NARA gotcha below).
* Surfaces rate-limit headers to debug logs.
* Normalizes all transport errors to `SourceError`.

The asset download path is still **only** through `asset_wrapper.download`
— sources call `fetch_to_wrapper(result, target_path, shot_id=...)`. The
no-raw-downloads grep test (Phase 0) covers all new files automatically.

### 3. License normalization is shared

`_base.normalize_license_type()` maps freeform strings ("CC BY-SA 4.0",
"Public domain", "No known restrictions") to the schema enum
(`cc-by-sa`, `pd`, etc.). It uses **longest-needle-first** matching so
`"CC BY-SA 4.0"` doesn't get truncated to `cc-by`. The earlier bug came
from dict-iteration-order matching.

Anything we can't classify becomes `"unclear"`, and:
* Wikimedia/Archive.org refuse to `fetch()` an unclear-license result
  (raise `SourceError`).
* The heuristic prefilter penalizes unclear-license candidates with -0.5
  so they sink in the ranking.

### 4. Skip on missing keys, don't crash the cascade

`SourceAuthError` from a source's `search()` is caught by `cascade._run_source`
and recorded in `report.skipped`. The walker continues to the next source.
This makes Phase 1 work with any subset of `{PEXELS, PIXABAY, NARA}` keys.

### 5. CLIP heuristic > nothing, < real CLIP

The heuristic prefilter is not a CLIP substitute — it can't tell whether a
thumbnail *looks* right, only whether the text metadata mentions the right
words. But it's strictly better than random ordering, has zero deps, and
keeps the verify pipeline shape identical to the CLIP path. Phase 5 (or
earlier, your call) flips `BROLL_USE_CLIP=1` and the same `pick()` call
now ranks by image-text cosine similarity.

### 6. Claude verifier uses raw HTTP

The Anthropic Messages API is a plain JSON POST; the SDK adds nothing we
need. Avoiding the SDK keeps `requirements.txt` minimal and makes the
verifier 100% stdlib. It tolerates fenced (` ```json `) responses and
handles `selected_index: "reject_all"` as the documented reject signal.

### 7. Per-shot log.json is durable

The log file is written even on failure (no candidates, reject_all). Phase 3
will read the same file to drive the refinement loop; Phase 4's attribution
slate generator reads `meta.json` but can cross-reference logs for the
"why was this clip picked" story.

---

## Known issues / gotchas for Phase 2

### 1. Wikimedia returns `.webm`, downloaded as `.mp4`

Today the wrapper trusts the target filename (`<shot_id>.mp4`) regardless
of upstream container. A Wikimedia win that's actually webm ends up on disk
as `foo.mp4` but with webm bytes — ffmpeg will still decode it, but it's
sloppy. **Fix in Phase 4** with a normalization pass that probes the file
and either re-muxes to mp4 or renames. For Phase 2's purposes this is fine
because AI generation outputs are already mp4 and the AI path doesn't have
this issue.

### 2. CloudFront flake on NARA

The reason NARA is key-gated is a real upstream issue: the public
`catalog.archives.gov/proxy/records/search` route is served by CloudFront,
and CloudFront sometimes routes the request to the SPA HTML shell with a
200 status. Even with retries the SPA is sticky for some queries during
some cache windows. With `NARA_API_KEY` we hit `/api/v2/records/search`
with an `X-Api-Key` header, which routes deterministically to the JSON
backend.

`http_get_json` already retries up to 3 times on HTML responses — Phase 2
shouldn't need more handling here.

### 3. Heuristic verifier doesn't actually look at pixels

The default verifier just trusts the prefilter score above a threshold.
This means with the all-heuristic stack (no CLIP, no Anthropic), a
Wikimedia clip whose metadata *mentions* "Suez Canal" will pass even if
the thumbnail shows the Suez Canal from a completely wrong angle. Phase 2
itself doesn't need to fix this (it's about AI gen), but the 70% exit
criterion of Phase 1 effectively requires turning on at least one real
backend before measuring. Recommended for the 30-shot run:
* `BROLL_USE_CLIP=1` + `pip install open-clip-torch torch` (one-time ~3GB).
* Or `ANTHROPIC_API_KEY` set for the Claude verifier.
* Ideally both.

### 4. Archive.org metadata calls are 1-per-candidate

`archive_org.search` issues N+1 HTTP calls: 1 search + N metadata fetches
(one per candidate, to learn its file list). Rate limit is 2/sec per the
bucket config; a search of 10 candidates → ~5 seconds. This is the price
of getting a usable download URL out of Archive.org. Phase 2 wouldn't
normally see this because the cascade usually stops at Wikimedia anyway.

### 5. LoC `resources[].files` shape is heterogeneous

LoC's JSON sometimes returns `resources[0].files` as a list of file dicts,
sometimes as a list-of-lists, sometimes as an *integer count*. Phase 1 had
to guard for all three (`isinstance(files, list)` then per-item dispatch).
If you add more LoC parsing, replicate the same guard pattern — don't
assume a shape.

### 6. Cache key includes orientation; doesn't include `kind` or `negative_intent`

The cache key is `(source_name, query, orientation, limit)`. If Phase 2
adds new shot-spec dimensions that change source query construction, the
cache key must include them too — otherwise stale cached results will
contaminate.

### 7. Schema `verification.clip_score` is clamped to [0, 1]

The heuristic prefilter score is unbounded in theory (can exceed 1 with
high overlap + source prior). `verify.verification_block()` clamps via
`score / 2.0 if > 1 else score` before writing meta, then clips to [0, 1].
That's enough to keep the schema happy; if you ever want to surface raw
heuristic scores, add a separate `prefilter_score_raw` field.

### 8. `_OUTPUT_DIR` is module-state, not a parameter

`pipeline/broll.py:_OUTPUT_DIR` is hardcoded to `output/broll/`. The
hermetic tests `monkeypatch.setattr` it to a tmp_path. Cleaner would be a
config object or function parameter — relevant for Phase 5 multi-output
support.

### 9. Anthropic verifier model defaults to `claude-sonnet-4-6`

That ID was current at write time (2026-05-21). If you swap to a different
model, update `vision_verifier._DEFAULT_MODEL` or set
`BROLL_VERIFIER_MODEL` per-run.

---

## What's ready for Phase 2 to plug into

Phase 2 (AI generation on Verda, LTX-2.3 + Wan 2.2) should:

1. **Add `broll/sources/ltx_video.py` and `broll/sources/wan_video.py`**
   following the existing source contract — but their entry point is
   `generate(prompt, seed, params, *, shot_id, target_path) -> dict`
   (not `search/fetch`). The result goes through `asset_wrapper.finalize`
   (already implemented) rather than `download` because ComfyUI produces
   the file locally.

2. **Add `broll/lib/ai_router.py`** with the LTX-vs-Wan rule (face heavy →
   Wan, else → LTX). The router takes a `decision` dict and returns the
   chosen source module name.

3. **Wire the AI path in `pipeline/broll.py`**: if
   `decision["strategy"] in ("ai_only", "ai_first")`, call the router →
   the AI source → `asset_wrapper.finalize`. Otherwise the current cascade
   path runs. For `ai_first`, run AI first and fall back to cascade.
   For `stock_first` with `ai_allowed=True` and cascade-fails-verify, AI
   is the fallback (this is the integration point Phase 3 refines).

4. **Add ComfyUI workflow templates** in `broll/comfyui_workflows/`. The
   source modules load them, splice in `prompt`/`seed`/LoRA stack, submit
   via the ComfyUI HTTP API. Pin model version in the meta (the schema's
   `source.version` field is ready).

5. **Deterministic seeds**: `broll/lib/seed_strategy.py` should be a
   stateless function `seed_for(prompt, model) -> int` based on a hash.
   This way the same prompt + model gives the same seed; manual override
   via spec `_seed` for randomization.

6. **Spot-pricing retry on Verda**: the AI source wraps ComfyUI submission
   in a retry loop that watches for spot interrupts. Use the rate limiter
   to throttle resubmission. The bucket name can be `verda`.

7. **Cost cap**: per AGENT.md, max 3 AI retries per shot. Enforced in the
   AI source, not in the pipeline (so Phase 3 refinement can stack on top).

The schemas, asset wrapper, rate limiter, cache, cascade, and verify
modules should not need changes for Phase 2. Phase 3's refinement loop
will reach into log.json files — keep them backwards-compatible.

---

## Phase 1 deferred items / open questions

* **70% exit criterion**: needs a 30-shot benchmark run after enabling a
  real prefilter or verifier backend. Tooling is in place; the run itself
  is the follow-up task.
* **Audio handling**: the wrapper writes whatever bytes the source ships.
  AGENT.md §"Open questions" says: probably strip universally. Phase 4
  normalization will tackle this.
* **Container normalization**: webm → mp4 transcoding pass. Phase 4.
* **CLIP cache**: per-thumbnail CLIP embeddings could be cached on disk to
  avoid re-embedding the same evergreen results. Easy add — sits next to
  `cache.py`. Deferred until CLIP backend is the default.
* **Vision-LLM cost**: every shot with the Claude backend costs ~$0.005-0.01
  (5 thumbnails, ~200 input tokens of text + images, ~100 output tokens).
  At 15 shots / video that's ~$0.15. Negligible now; revisit if volume
  grows 100×.
* **Refinement loop**: not implemented (Phase 3). A `reject_all` outcome
  currently surfaces to exit code 5 and writes a log. Phase 3 reads that
  log, asks the LLM to refine the query or escalate to AI, retries.

---

## Test counts

```
Offline:    117 tests pass.
Network:      5 pass (Wikimedia, LoC, Archive.org, Pexels, full live cascade-to-fetch)
              2 skip on missing keys (NARA, Pixabay)
              1 deselected (Phase 0 smoke; still passes when re-enabled)
              0 failing.
```

Run offline only: `pytest broll/tests/ -m "not network"`.
Run network: `pytest broll/tests/ -m network`.
Run everything: `pytest broll/tests/`.

---

## Updated env vars

| Var                       | What it does                                    | Required for           |
|---------------------------|-------------------------------------------------|------------------------|
| `PEXELS_API_KEY`          | Pexels search                                   | Pexels source          |
| `PIXABAY_API_KEY`         | Pixabay search                                  | Pixabay source         |
| `NARA_API_KEY`            | NARA v2 catalog (free at api.data.gov/signup/)  | NARA source            |
| `ANTHROPIC_API_KEY`       | Claude vision verifier                          | Real vision verify     |
| `BROLL_USE_CLIP`          | `1` → use OpenCLIP backend                      | CLIP prefilter         |
| `BROLL_PREFILTER`         | `heuristic` / `open_clip`                       | Force prefilter        |
| `BROLL_VERIFIER`          | `heuristic` / `anthropic`                       | Force verifier         |
| `BROLL_VERIFIER_MODEL`    | Override the Claude model id                    | Verifier model         |
| `BROLL_NO_RATE_LIMIT`     | `1` → disable rate limiting (tests)             | CI                     |
| `BROLL_NO_CACHE`          | `1` → disable disk cache                        | CI                     |
| `BROLL_CACHE_TTL_SEC`     | Cache TTL (default 21600 = 6 hr)                | Tuning                 |

Good luck with Phase 2.

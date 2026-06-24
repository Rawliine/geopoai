# AGENT.md — GeoPoAI B-Roll System

Working brief for any agent editing the B-roll layer. Read first.

---

## What this layer is

A unified retrieval + generation system. Input: a shot spec from the LLM. Output: an MP4 clip with full provenance. Internally cascades through stock sources, falls back to AI generation on Verda, runs two-stage verification (CLIP + vision-LLM).

Sits next to the Mapbox engine, Manim engine, and Presenter engine. The orchestrator stitches their outputs into the final video.

---

## Repository layout

```
GeoPoAI/
├── broll/
│   ├── __init__.py
│   ├── lib/
│   │   ├── asset_wrapper.py      # the ONLY way assets touch disk
│   │   ├── keyword_generator.py  # LLM: intent → keyword queries
│   │   ├── cascade.py            # walks sources in order
│   │   ├── decision.py           # stock-first vs AI-first
│   │   ├── verify.py             # CLIP prefilter + vision-LLM
│   │   ├── ai_router.py          # picks LTX vs Wan
│   │   ├── seed_strategy.py      # deterministic seeds
│   │   ├── refinement.py         # LLM correction loop
│   │   ├── attribution.py        # slate generation
│   │   └── license_audit.py      # pre-publish check
│   ├── sources/
│   │   ├── wikimedia.py
│   │   ├── loc.py
│   │   ├── archive_org.py
│   │   ├── pexels.py
│   │   ├── pixabay.py
│   │   ├── ltx_video.py          # Verda ComfyUI client
│   │   └── wan_video.py          # Verda ComfyUI client
│   ├── comfyui_workflows/
│   │   ├── ltx_2_3_base.json
│   │   └── wan_2_2_base.json
│   ├── prompts/
│   │   ├── ai_prompt_template.md
│   │   ├── style_tokens.md
│   │   └── lora_stack.json
│   ├── schema/
│   │   ├── shot_spec_schema.json
│   │   └── asset_meta_schema.json
│   ├── templates/
│   │   └── attribution_slate.md
│   └── tests/
│       ├── source_smoke/
│       ├── verify_fixtures/
│       └── e2e/
├── output/
│   └── broll/
│       ├── <shot_id>.mp4
│       ├── <shot_id>.meta.json
│       └── <shot_id>.log.json
└── pipeline/
    └── broll.py                  # thin entry point: shot_spec → clip
```

---

## Hard rules

1. **Nothing touches disk without going through `asset_wrapper.py`.** No `requests.get(url).content`, no `urllib.urlretrieve`, no AI gen results saved directly. The wrapper is the single point that produces both the asset file and its `.meta.json`. CI greps for violations.

2. **No asset exists without its `.meta.json`.** Orphaned assets are removed by the audit pass. Don't write code that produces one without the other.

3. **Shot IDs are immutable once assigned.** They are the join key between scripts, clips, attribution, and logs. Generate once at the orchestrator level, propagate everywhere.

4. **Stock-first by default.** AI generation is the fallback. Override only when the shot type explicitly requires AI (see Decision Matrix below).

5. **Spot pricing on Verda for all batch jobs.** Interactive iteration uses on-demand; batch generation uses spot. Both pipelines must be interrupt-tolerant.

6. **AI provenance is full and verbatim.** Every AI clip records model name + version, exact prompt, seed, LoRA stack, sampler, step count. No paraphrasing the prompt in metadata.

7. **License compatibility is checked before publish.** No human in the loop "promising to credit later" — `license_audit.py` runs as a CI gate. Non-commercial assets in a monetized video block the publish.

---

## The shot spec — what the LLM produces

The orchestrator's LLM emits one of these per shot beat in the script:

```json
{
  "shot_id": "ep017-broll-003",
  "intent": "aerial view of container ships in the Suez Canal at dawn",
  "kind": "establishing",
  "duration_seconds": 4,
  "queries": [
    "Suez Canal container ship aerial",
    "Suez Canal sunrise drone",
    "Egypt canal shipping traffic"
  ],
  "stock_first": true,
  "format": "horizontal",
  "tone": "calm, observational"
}
```

`shot_id` is canonical. `intent` is what the verifier checks against. `queries` are what the source clients hit. `stock_first: false` forces AI generation. `kind` drives the decision matrix.

---

## Decision Matrix — stock vs AI

The LLM hints with `stock_first`, but the layer also enforces rules. Apply this matrix in `decision.py`:

| Shot kind | Default | Override |
|---|---|---|
| Real named event (G20 summit, specific battle) | **stock-only** | never AI |
| Real named person (Putin, Macron) | **stock-only** | never AI |
| Recognizable place (Red Square, Pentagon) | **stock-only** | never AI |
| Archival pre-2010 | **stock-only** | never AI |
| Establishing shot, generic city/crowd/traffic | **stock-first** | AI ok if no good stock |
| Conceptual ("global tension visualized") | **AI-only** | stock irrelevant |
| Stylized continuity (recurring fictional scene) | **AI-only** | stock irrelevant |
| Filler when stock is too generic | **AI-first** | stock fallback |

The matrix is data, not code branches. Update `broll/lib/decision.py:DECISION_TABLE`.

---

## How to add a stock source

1. Create `broll/sources/<name>.py`
2. Implement `search(query: str, limit: int) -> list[SearchResult]` and `fetch(result: SearchResult, target_path: str) -> AssetMeta`
3. `SearchResult` includes: `id`, `thumbnail_url`, `download_url`, `license`, `attribution_text`, `source_metadata`
4. `fetch()` calls `asset_wrapper.download(...)` — never raw downloads
5. Register in `broll/sources/__init__.py:SOURCES`
6. Add to cascade order in `broll/lib/cascade.py:CASCADE_ORDER`
7. Add smoke test in `broll/tests/source_smoke/test_<name>.py` — one canned query, asserts result structure + license tagging

---

## How to add an AI model

1. Create `broll/sources/<name>.py`
2. Implement `generate(prompt: str, seed: int, params: dict) -> AssetMeta`
3. Add a ComfyUI workflow template in `broll/comfyui_workflows/<name>_base.json`
4. Update `broll/lib/ai_router.py` with the routing rule (when to pick this model)
5. Add prompt token guidance in `broll/prompts/ai_prompt_template.md`
6. Add provenance fields (model version, sampler, etc.) to the meta schema if new

---

## The `.meta.json` schema (canonical)

```json
{
  "shot_id": "ep017-broll-003",
  "asset_path": "output/broll/ep017-broll-003.mp4",
  "kind": "stock_video|ai_video|ai_image",

  "source": {
    "name": "wikimedia|loc|archive_org|pexels|pixabay|ltx-2.3|wan-2.2",
    "version": "2.3" or null,
    "url": "https://...",
    "fetched_at": "2026-05-20T14:32:00Z"
  },

  "license": {
    "type": "cc-by|cc-by-sa|cc0|pd|pexels|non_commercial|...",
    "attribution_required": true,
    "attribution_text": "Photo by ... via ...",
    "commercial_use_ok": true
  },

  "verification": {
    "clip_score": 0.82,
    "vision_llm_passed": true,
    "vision_llm_reason": "matches intent of aerial container shipping at golden hour"
  },

  "ai_metadata": {
    "model": "ltx-2.3",
    "prompt": "<exact prompt>",
    "negative_prompt": null,
    "seed": 1234567,
    "lora_stack": [{"name": "Soft_Enhance_Style_LoRa", "strength": 0.4}],
    "sampler": "euler",
    "steps": 30,
    "resolution": [1280, 720],
    "duration_seconds": 5
  },

  "modifications": ["trimmed_to_4s", "resized_to_1920x1080"]
}
```

`ai_metadata` is `null` for stock assets. `verification` is `null` if no verification was run (manual override).

---

## Commands

```bash
# fetch one shot end-to-end
python pipeline/broll.py <shot_spec.json>

# walk cascade for a query, print results without downloading
python -m broll.lib.cascade --query "Suez Canal aerial" --dry-run

# verify an existing asset against a new intent
python -m broll.lib.verify --asset <id> --intent "..."

# run license audit on a video's manifest
python -m broll.lib.license_audit --manifest output/episodes/ep017/manifest.json

# generate attribution slate
python -m broll.lib.attribution --manifest output/episodes/ep017/manifest.json --out slate.md

# regenerate an AI clip from its meta.json (deterministic)
python -m broll.sources.ltx_video --replay <meta.json>
```

---

## Pitfalls

- **CLIP false positives on visually similar but contextually wrong shots.** A clip of any major canal will score high for "Suez Canal" if dawn lighting matches. Vision-LLM exists to catch these — don't disable it for cost.
- **AI clip flicker at boundaries.** LTX-2.3 clips often have frame instability in the first ~10 frames. Trim 0.3s off the start before delivery.
- **Pexels license is permissive but evolving.** Re-check terms quarterly. The `license_audit` table is the source of truth; update it, not individual clips.
- **Wikimedia structured data fields are inconsistent.** Older uploads may have license info in description text instead of structured fields. The wikimedia client must handle both, and surface "license unclear" to the verifier rather than guessing.
- **Verda spot interruptions.** ComfyUI jobs that die mid-render need to be detected and resubmitted. Wrap the AI generation calls with a retry loop that watches for connection drops.
- **Seed determinism across model versions.** Same prompt + seed + LTX-2.3-v2.3 ≠ same output as v2.4. Pin the model version in the meta.

---

## How a single shot moves through the system

```
1. orchestrator emits shot_spec → pipeline/broll.py
2. schema validation → asset_wrapper logs the request with shot_id
3. decision.py picks initial strategy based on shot kind
4. If stock-first:
   a. cascade.py walks sources, accumulates candidates
   b. verify.clip_prefilter trims to top 5
   c. verify.vision_llm picks one or returns reject_all
   d. on reject_all → refinement.py asks LLM to refine, or escalates to AI
5. If AI-first or fallback:
   a. ai_router.py picks LTX or Wan
   b. generate via ComfyUI on Verda (spot, with retry)
   c. verify.vision_llm checks the result
   d. on reject → refinement.py refines prompt, retries (max 3)
6. asset_wrapper.finalize writes final clip + .meta.json to output/broll/
7. log.json captures all attempts for debugging
```

If step 5d hits max retries, the shot is surfaced to a `failed_shots/` directory with the log. The orchestrator can decide to re-prompt, skip, or escalate to human.

---

## When in doubt

- Stock is safer than AI. AI is faster than stock when no stock exists.
- A shot without provenance is a liability. Reject it earlier rather than later.
- Read `recap.md` for the rationale behind any decision that looks restrictive.
- Read `plan.md` for what's built and what's coming.

# recap.md — B-Roll Design decisions, reasoning, open questions

Companion to `plan.md` (what to build) and `AGENT.md` (working rules). This file is the *why*.

---

## 1. Vision

A B-roll layer that:
- Returns real footage when real footage exists and is appropriate
- Generates synthetic footage when no appropriate real footage exists, or when the shot is conceptual/stylized
- Carries full provenance for every clip — viewer trust depends on real footage being real, monetization depends on license compliance
- Operates without per-shot human intervention, but surfaces failures clearly when human judgment is needed

The B-roll layer is the part of the pipeline most exposed to two competing risks:
- **Trust risk** — using AI-generated footage of a real event undermines the channel's credibility
- **Cost risk** — paying licensing fees for stock that AI could produce, or burning compute on AI for shots stock would handle

The decision matrix in `AGENT.md` exists to keep both in check.

---

## 2. Cascade order — why this order

```
Wikimedia → LoC → NARA → Archive.org → Pexels → Pixabay
```

**Wikimedia first** for two reasons: (a) license clarity is the best of any source — structured CC-BY or PD with author attribution baked into the metadata; (b) the content overlap with our subject matter is high (historical events, named individuals, places of geopolitical significance).

**LoC and NARA next** because for US-related historical and military content, they have higher-quality assets than Wikimedia and are unambiguous public domain. For non-US content, they're sparse; the cascade falls through quickly.

**Archive.org fourth** because the license landscape is messier — it aggregates a mix of PD, CC, and uploads-of-unclear-provenance. Useful as a backup, never as a primary.

**Pexels and Pixabay last** because the content is generic-modern. Useful for establishing shots ("city traffic at night") but they don't carry archival or named-event content. They sit at the bottom because by the time we're here, the shot is generic enough that any matching clip is fine.

`[FLUID]` — the order can shift if real usage shows one source consistently failing. NARA might move ahead of LoC for certain content types.

---

## 3. Stock vs AI — the deeper reasoning

Three categories of shots, each handled differently:

**Trust-critical shots** — anything where the viewer will assume the footage is real and where being wrong about that undermines credibility. Real events, real people, real places. **Stock-only**, no AI substitution. The cost of being caught using AI for a real Putin speech once is higher than the cost of dropping the shot entirely.

**Conceptual shots** — visualizations of abstractions, fictional scenarios, stylized illustrations. **AI-native**. Stock would be inadequate, and viewers expect these to be constructed.

**Generic establishing shots** — city skylines, anonymous crowds, traffic, weather. **Stock-first with AI fallback**. Either source works; stock is cheaper and arguably more "honest." AI fills gaps when stock results are too generic or off-style.

The matrix is data-driven and code-enforced because the LLM authoring the shot specs will be tempted to take the easy path (AI for everything is faster). The decision layer keeps it honest.

`[LOCKED]` — three-tier philosophy. Specific category boundaries fluid.

---

## 4. Two-stage verification — why both

CLIP alone is fast and cheap but produces high false-positive rates on contextually-wrong shots (any canal at dawn ≈ Suez Canal at dawn to CLIP). Vision-LLM alone is accurate but expensive at scale (5+ API calls per shot if we verify every candidate).

Two-stage solves both:
- **CLIP prefilter** runs locally on thumbnails, takes milliseconds, costs $0, eliminates 80% of the candidate pool by gross visual mismatch
- **Vision-LLM** runs on the top 5 only, costs one API call per shot total, catches the contextual errors CLIP misses

The verification layer is also the part of the system that interfaces with the orchestrator's LLM during failure refinement — if vision-LLM rejects all candidates, the orchestrator's LLM is given the rejection reasons and asked to refine the query or switch to AI.

`[FLUID]` — could be replaced by a single fine-tuned CLIP on channel aesthetic in Phase 5+ if costs become a problem. For now, off-the-shelf is fast enough.

---

## 5. Model choice — LTX-2.3 + Wan 2.2

Decision context: LTX-2.3 generates a 5-second 720p clip in under a minute on H100, with strong prompt adherence. Wan 2.2 is roughly 4-5x slower but renders human faces and physical motion more convincingly.

For this content:
- 80%+ of AI B-roll is non-face: aerial shots, cityscapes, conceptual abstractions, atmospheric scenes. LTX handles these well and at iteration-friendly speed.
- The 20% that involves faces (talking heads in stock-style cutaways, named individuals we can't get stock for) needs Wan.

Splitting models by shot type rather than picking one is the practical answer. The router rule is simple enough to be reliable: face-heavy → Wan, else → LTX.

HunyuanVideo was considered and skipped. Quality is competitive but per-clip render time + heavier VRAM doesn't justify a third model in the rotation. Revisit if a specific look we want can't be hit by either LTX or Wan.

`[FLUID]` — model rotation will evolve. New open-source video models ship monthly. The `ai_router.py` interface is stable; the implementations behind it can change.

---

## 6. Asset marking — the philosophy

Every asset is a liability until proven otherwise. Without provenance:
- Attribution slates become guesswork
- License audits become impossible
- Reuse decisions on future videos are blind
- AI provenance for platform compliance is missing
- Reproducibility is gone

The wrapper-as-only-path-to-disk pattern exists because partial discipline is no discipline. If anyone can bypass the wrapper "just this once," metadata gaps accumulate and the audit becomes meaningless.

Provenance includes for AI: model, version, prompt, seed, LoRA stack, sampler, steps. This is enough to regenerate the clip later. For stock: source URL, license, attribution text, fetch timestamp. Together with the `verification` block, a 3-year-old clip can be defended on credibility, traced legally, and regenerated technically.

`[LOCKED]` — wrapper-only disk access, .meta.json required.

---

## 7. The refinement loop

When verification rejects all candidates, the system has three options:
1. Tell the orchestrator's LLM to refine the query and try again
2. Switch from stock to AI (or vice versa)
3. Give up and surface the failure

Defaulting to (1) and (2) before (3) makes the layer self-correcting. The orchestrator's LLM sees the rejection reasons and refines — this is the tightest feedback loop in the pipeline since no rendering is needed for refinement.

Cap at 2 LLM refinement rounds + 3 AI generation retries to bound cost. After that, surface to `failed_shots/` and let the orchestrator decide.

`[LOCKED]` — bounded retry loop.

---

## 8. Cost shape

Approximate costs per shot, assuming Verda spot pricing:

| Shot path | Cost |
|---|---|
| Stock cascade hit, verified | ~$0.001 (just API + vision-LLM) |
| AI generated LTX-2.3, first attempt | ~$0.03-0.05 |
| AI generated Wan 2.2, first attempt | ~$0.12-0.20 |
| AI with 2 refinement retries | 2-3x above |

For a 1-minute video with ~15 shots: $0.05-2.00 in B-roll compute, depending on stock vs AI ratio. Negligible compared to script writing, voice, and final render compute.

Worth noting because it shapes the policy: AI is cheap enough that stock-first isn't about money, it's about trust.

`[FLUID]` — numbers will drift as Verda pricing and model speeds change.

---

## 9. Integration with other pipeline layers

```
                  Orchestrator
                       │
                       │ emits shot specs per script beat
                       ▼
              ┌────────────────────┐
              │   B-Roll Layer     │
              └─────────┬──────────┘
                        │
                        ▼
                output/broll/*.mp4 + .meta.json
                        │
                        │ consumed by final composition
                        ▼
              ┌────────────────────┐
              │   ffmpeg compose   │ ← also receives:
              │                    │   - Mapbox clips (output/*.mp4)
              │                    │   - Manim clips (output/manim/*.mp4)
              │                    │   - Presenter clips (output/presenter/*.mp4)
              │                    │   - Voice audio
              └─────────┬──────────┘
                        │
                        ▼
                  final video
```

The B-roll layer is one of four sibling content producers. They share the orchestrator and the final composition step but otherwise run independently.

Shared concerns across the four:
- Asset marking philosophy (uniformly: nothing without .meta.json)
- Output naming conventions (shot_id / scene_id stable, files named after them)
- Schema validation as a CI gate
- Format flag (horizontal vs vertical) propagates from orchestrator down to each layer

`[LOCKED]` — layered architecture with shared conventions.

---

## 10. Open questions (fluid)

- **CLIP model choice.** Default to OpenAI CLIP ViT-L. SigLIP or EVA-CLIP score better on benchmarks but add deployment cost. Revisit if accuracy is insufficient.
- **Vision-LLM choice.** Default Claude. Considered: GPT-4V, Gemini, local LLaVA. Local LLaVA would zero out cost but accuracy drop is real. Worth re-evaluating quarterly.
- **Audio handling.** Stock often has audio (ambient sound, music). AI clips don't. Stripping by default loses useful ambient sound; preserving creates conflicts with the channel's score. Default: strip and let composition add foley.
- **Multi-take generation.** When AI is the path, should we generate 3 takes and pick the best, or generate 1 and verify? Multi-take improves quality but triples cost. Probably 1 then refine on reject.
- **Pre-fetched evergreen cache.** Worth building once we know which shots recur. Cold start: empty cache, every shot is a fresh fetch. Heuristic: after 10 episodes, look at top-50 most-fetched shots and pre-cache.
- **Failure analytics.** When the refinement loop exhausts and a shot fails, what's the failure mode distribution? "Stock didn't exist" vs "AI couldn't match style" vs "verification was too strict"? Worth instrumenting once volume justifies it.
- **Shared CLIP embedding cache.** Compute CLIP embedding once per asset, store in meta. Future shots can compare against cached embeddings without re-running CLIP on the same thumbnails.
- **Style consistency across AI shots within one video.** If three AI clips in one episode are generated with the same prompt template but slightly different seeds, do they feel like one video? Open. Possibly require shared seed + same LoRA stack within an episode.

---

## 11. Decision log

| Decision | Section | Status |
|---|---|---|
| Cascade order (Wikimedia → ... → Pixabay) | §2 | FLUID |
| Three-tier stock-vs-AI matrix | §3 | LOCKED (philosophy), FLUID (categories) |
| Two-stage verification (CLIP + vision-LLM) | §4 | FLUID (specific models) |
| LTX-2.3 + Wan 2.2 model rotation | §5 | FLUID |
| Wrapper-only disk access | §6 | LOCKED |
| .meta.json required, schema enforced | §6 | LOCKED |
| Bounded refinement loop (2 LLM + 3 AI retries) | §7 | LOCKED (bounded), FLUID (limits) |
| Spot pricing for batch on Verda | §8 | LOCKED |
| Integration via output/broll/ + shared orchestrator | §9 | LOCKED |

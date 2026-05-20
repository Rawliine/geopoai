# HANDOFF — B-Roll Phase 2 → Phase 3

Written: 2026-05-21. Author: agent that built Phase 2.
Read this before touching Phase 3. Then read `AGENT(1).md`, `plan(1).md`,
`recap(1).md`, `HANDOFF_PHASE_0.md`, and `HANDOFF_PHASE_1.md`.

---

## TL;DR

Phase 2 is **functionally complete** with **176/176 offline tests passing**.
The AI generation pipeline is wired end-to-end against a mock ComfyUI
server (HTTP fixture), so every code path through the AI sources, the
router, the cache, and the strategy dispatch is exercised without
touching Verda. A real Verda smoke run is a one-line config flip away —
see "How to verify against real Verda" below.

What ships:
* **ComfyUI HTTP client** with retry-on-spot-interrupt semantics.
* **Two AI sources** (LTX-2.3, Wan 2.2) sharing one base class.
* **Workflow templates** with slot markers (``<<PROMPT>>``, ``<<SEED>>``…).
* **Deterministic seed strategy** + **recipe-keyed disk cache** (free reruns).
* **AI router** (LTX vs Wan, face-heuristic + explicit override).
* **Prompt assembler** with house-style tokens, tone blocks, and a
  per-model word budget that never truncates the user's intent.
* **Strategy dispatcher** in ``pipeline/broll.py`` that handles
  ``stock_only``, ``stock_first``, ``ai_first``, ``ai_only`` with
  fallbacks where the decision matrix allows them.
* **Per-shot ``.log.json``** capturing decision, cascade report, verify
  report, AI generation record, final outcome.

What's deferred to Phase 3:
* The LLM refinement loop. Today, reject-all and AI-failure surface as
  exit codes; Phase 3 reads the log.json, asks the LLM to refine the
  prompt or queries, and retries (bounded).

---

## What was built

### Files added (Phase 2)

```
broll/
├── HANDOFF_PHASE_2.md            ← this file
├── prompts/
│   ├── ai_prompt_template.md      ✅ docs the assembler
│   ├── style_tokens.md            ✅ fenced positive/negative/tone blocks
│   └── lora_stack.json            ✅ default + per-model LoRA stacks
├── comfyui_workflows/
│   ├── ltx_2_3_base.json          ✅ LTX text-to-video reference
│   └── wan_2_2_base.json          ✅ Wan text-to-video reference
├── lib/
│   ├── comfyui_client.py          ✅ HTTP client: submit, poll, view
│   ├── seed_strategy.py           ✅ deterministic + override
│   ├── prompt_assembly.py         ✅ build_prompt + LoRA loader
│   └── ai_router.py               ✅ LTX vs Wan
├── sources/
│   ├── _ai_base.py                ✅ BaseAIGenerator (lifecycle + cache)
│   ├── ltx_video.py               ✅ LTXVideoGenerator + replay CLI
│   └── wan_video.py               ✅ WanVideoGenerator + replay CLI
└── tests/
    ├── _comfyui_mock.py           ✅ stateful local HTTP fixture
    ├── test_comfyui_client.py
    ├── test_seed_strategy.py
    ├── test_prompt_assembly.py
    ├── test_ai_router.py
    ├── test_ai_sources.py         ✅ full ComfyUI lifecycle
    └── test_phase2_pipeline.py    ✅ all 4 strategies routed end-to-end

pipeline/broll.py                  ↻ rewired for the 4 strategies
broll/sources/__init__.py          ↻ exposes AI_SOURCES registry
```

### How the strategies route

The decision matrix from Phase 0 emits one of four strategies; Phase 2's
pipeline maps them as follows:

| Strategy        | Path                                                            | Fallback                                         |
|-----------------|-----------------------------------------------------------------|--------------------------------------------------|
| ``stock_only``  | cascade → verify → fetch                                        | none; reject/empty surfaces as exit 4 or 5       |
| ``stock_first`` | cascade → verify → fetch                                        | AI if ``ai_allowed`` and stock fails             |
| ``ai_first``    | AI generation                                                   | stock cascade if AI fails (any reason)           |
| ``ai_only``     | AI generation                                                   | none; AI failure surfaces as exit 6              |

`ai_allowed` is from the decision matrix: kinds marked ``real_named_*``,
``recognizable_place``, ``archival_pre_2010`` cannot fall back to AI even
when their cascade fails — that's the credibility constraint.

### AI generation lifecycle

For a single AI shot, ``BaseAIGenerator.generate(spec, target)``:

1. **Assemble** the prompt via :mod:`broll.lib.prompt_assembly`. Intent
   is preserved verbatim; tone block and channel positive tokens are
   appended. Negative prompt combines channel negatives + per-shot
   ``negative_intent``.
2. **Derive the seed** via :func:`seed_strategy.seed_from_spec`. Honors
   ``shot_spec._seed`` override; otherwise hashes ``(prompt, model,
   lora_stack, salt)`` to a stable 32-bit unsigned int.
3. **Compute the recipe key** — SHA-256 of the full recipe (model,
   prompt, negative, seed, sampling params, LoRA stack).
4. **Cache check**. If a file exists at
   ``data/.cache/broll/ai_recipes/<recipe_key>.mp4``, we skip ComfyUI
   entirely and finalize from the cache.
5. **Substitute slots** in the workflow JSON template — every
   ``"<<KEY>>"`` string in the template is replaced by the corresponding
   value (positive prompt, seed, steps, width, etc.). Empty LoRA slots
   are auto-disabled (``lora_name="none"`` + strength=0) so missing
   LoRA files never crash the workflow.
6. **Submit** to ComfyUI via :class:`ComfyUIClient`. The client:
   * Retries the POST /prompt on transport errors.
   * Polls /history/<id> at 1.5 s intervals.
   * Tolerates up to 3 consecutive transport errors before giving up
     (spot interrupts present as connection drops).
   * Streams the output via /view into the recipe-cache path.
7. **Resubmit** if the whole job died. Up to ``max_resubmits=2`` extra
   attempts. The seed is preserved across resubmissions.
8. **Finalize** via :func:`asset_wrapper.finalize`. When the cache is
   enabled, finalize uses ``move=False`` so the cache file persists for
   future hits.

### `.meta.json` shape for AI shots

Identical to the Phase 0 schema — ``kind: "ai_video"`` triggers the
``ai_metadata`` required block:

```json
{
  "shot_id": "phase2-cli-001",
  "asset_path": "output/broll/phase2-cli-001.mp4",
  "kind": "ai_video",
  "source": {
    "name": "ltx-2.3",
    "version": "2.3",
    "url": "comfyui://ltx-2.3/<shot_id>",
    "fetched_at": "2026-05-20T22:27:22Z",
    "source_metadata": {
      "from_recipe_cache": false,
      "fps": 24, "num_frames": 72, "resolution": [1280, 720]
    }
  },
  "license": {
    "type": "ai_generated", "attribution_required": false,
    "commercial_use_ok": true,
    "attribution_text": "Generated with ltx-2.3 (recipe seed <N>)"
  },
  "verification": null,
  "ai_metadata": {
    "model": "ltx-2.3",
    "prompt": "<verbatim user intent>. <tone block>. <channel positive>.",
    "negative_prompt": "<channel negative>. <user negative>.",
    "lora_stack": [{"name": "Soft_Enhance_Style_LoRa", "strength": 0.4}],
    "seed": 3807364966,
    "sampler": "euler",
    "steps": 30,
    "resolution": [1280, 720],
    "duration_seconds": 3.0
  },
  "modifications": [],
  "schema_version": "1"
}
```

The `replay` CLI on each AI source rebuilds the exact recipe from the
meta and regenerates:

```bash
python -m broll.sources.ltx_video --replay output/broll/<shot_id>.mp4.meta.json
python -m broll.sources.wan_video --replay output/broll/<shot_id>.mp4.meta.json
```

This is the "6 months later, regenerate the same clip" guarantee from
``recap(1).md`` §6.

---

## How to verify against real Verda

The mock server proves the wire format; here's how to flip to the real
instance.

### 1. Bring up the ComfyUI box

Per ``infra/verda_workflow(2).md``:

```bash
cd infra
terraform apply -var="run_id=broll-$(date +%s)" \
  -var-file="workloads/comfyui.tfvars"
INSTANCE_IP=$(terraform output -raw instance_ip)
```

Wait ~60 s for the bootstrap script (`comfyui_bootstrap.tftpl`) to mount
the persistent volume and start ComfyUI on :8188 inside a tmux session.

### 2. Point the broll layer at it

```bash
echo "BROLL_COMFYUI_URL=http://${INSTANCE_IP}:8188" >> .env
```

(or export per-shell; the pipeline reads via ``load_dotenv``).

### 3. Run a single AI shot

```bash
cat > /tmp/ai_shot.json <<'EOF'
{
  "shot_id": "verda-smoke-001",
  "intent": "abstract visualization of global tension as flowing geometry",
  "kind": "conceptual",
  "duration_seconds": 3,
  "format": "horizontal",
  "tone": "tense"
}
EOF
python pipeline/broll.py /tmp/ai_shot.json --print-meta
```

You should see:
* Strategy decided as ``ai_only`` (conceptual kind).
* Router picks ``ltx-2.3`` (no face hint).
* ComfyUI submission → polling → download.
* ``output/broll/verda-smoke-001.mp4`` + ``.meta.json`` + ``.log.json``.

Roughly 60–90 s end-to-end on H100 spot for a 3-second LTX clip
(first run includes ~30 s model-warm; subsequent calls reuse VRAM).

### 4. Watch costs

```bash
# Use the rate limiter buckets and the recipe cache aggressively:
export BROLL_NO_AI_CACHE=  # default on — same prompt+seed never regenerates
python pipeline/broll.py /tmp/ai_shot.json  # second run: ~50 ms, no Verda traffic
```

### 5. Tear down

```bash
cd infra && terraform destroy -auto-approve \
  -var="run_id=<the run_id you used>" \
  -var-file="workloads/comfyui.tfvars"
```

The persistent volume (with model weights + LoRAs + ``data/.cache``)
stays. Re-applying the same `run_id` next time picks up exactly where
you left off.

### Workflow tuning

The bundled workflow templates target a vanilla LTX-Video 2.3 / Wan 2.2
ComfyUI setup. If your Verda volume uses different checkpoint filenames,
custom samplers, or extra LoRA chain links, edit
``broll/comfyui_workflows/<model>_base.json`` directly. The slot
markers (``<<PROMPT>>``, ``<<SEED>>``, ``<<WIDTH>>``, …) are the only
contract — keep those and the substitution engine works.

Currently only one LoRA slot is wired through. Multi-LoRA requires
chaining additional ``LoraLoader`` nodes in the template and adding
``LORA_1_NAME`` / ``LORA_1_STRENGTH`` slots. See gotcha #4 below.

---

## Architectural choices

### 1. Slot substitution by sentinel string

The workflow JSONs are valid ComfyUI graphs with ``"<<KEY>>"`` strings
in place of user-supplied values. ``_substitute_slots`` walks the dict,
replaces matching strings, and returns a populated graph. Pros: the
template can be opened in ComfyUI's UI for editing; the substitution
keeps JSON shape invariant; missing slots raise loudly at submission
time.

Cons: dynamic graph topology (variable-length LoRA chain, optional
img2vid input, etc.) requires graph-rewrite logic, not just
substitution. Phase 5+ may want to graduate to a real node-graph
builder; the interface (``BaseAIGenerator.generate``) doesn't change.

### 2. Recipe cache instead of ComfyUI's built-in cache

ComfyUI has a per-server output cache, but it's tied to one running
instance's filesystem. Once the spot instance dies, the cache dies.
Our recipe cache lives on the developer's box at
``data/.cache/broll/ai_recipes/`` and survives across Verda lifecycles,
making "regenerate this episode again next month" free.

The cache key includes every input that can change the output: model,
prompt, negative prompt, seed, sampling params, LoRA stack. Change any
one and the key changes.

### 3. Deterministic seed unless explicitly overridden

The default seed is ``hash(prompt + model + lora_stack + salt)``. Same
inputs = same seed = same clip = same cache key. The ``_seed``
override is for the rare case where you want a different roll without
changing the prompt; ``_seed_salt`` is for "I want a different one but
keep the recipe stable in the log."

### 4. Verda CLIENT_ID/SECRET are not the ComfyUI key

The ``VERDA_CLIENT_ID`` / ``VERDA_CLIENT_SECRET`` pair authenticates
Terraform with Verda's control plane; ComfyUI on the instance has no
auth. The pipeline only needs ``BROLL_COMFYUI_URL`` — the instance's
IP + port, behind whatever network controls you've put in place (in
the default Verda setup, the instance is on the public internet but
unauthenticated, which is fine for short-lived spot batches but
absolutely not for long-running servers; if you keep one up, put it
behind a Tailscale tunnel or set up basic-auth in nginx in front of
ComfyUI).

### 5. Heuristic face router, not pixel-based

``ai_router.pick_model`` matches whole-word face/portrait hints against
``intent + tone + negative_intent``. A handful of contradicting
"non-face" hints (``aerial``, ``cityscape``, ``abstract``) defeat a
borderline face match because LTX handles small-faces-in-wide-shots
fine. Phase 5+ could swap in a CLIP-based or thumbnail-based classifier;
the contract stays the same (``str -> "ltx-2.3" | "wan-2.2"``).

### 6. AI cache file IS the working file

In the fresh-gen path, the staging download writes directly into the
cache path; ``asset_wrapper.finalize(move=False)`` then COPIES it into
the target. The cache file is preserved. In the cache-hit path,
``local_path`` is already the cache path; same ``move=False`` path
applies. When the cache is disabled, the staging file is a one-off
temp and ``move=True`` cleans it up.

This is the cleanest way I found to keep the cache and the asset both
materialized without redundant copies. ``shutil`` and the wrapper do
the work; no special-case code in the AI base.

### 7. The ``filename_prefix`` slot writes outputs under
``ComfyUI/output/broll/<shot_id>_<NNNNN>.mp4`` on the server. We
download via ``/view`` and don't depend on inspecting the server-side
filename layout afterwards.

---

## Known issues / gotchas for Phase 3

### 1. Reject + AI fallback bypasses the verifier on the AI clip

Today, when ``stock_first`` falls back to AI because the verifier
rejected all stock candidates, the AI clip is delivered **without**
running it back through the verifier. That's by design for Phase 2 —
re-verification of AI is Phase 3 territory once the refinement loop
exists. But it means a bad AI clip can ship if you don't have the
Claude verifier turned on. Set ``ANTHROPIC_API_KEY`` and re-enable
verification in the AI path during Phase 3.

### 2. ComfyUI output node ID is hard-coded to "8"

The workflow templates name the ``VHS_VideoCombine`` (output) node
``"8"``. The ``filename_prefix`` slot writes a single output there.
If you reshape the template to use a different saver (e.g. SaveAnimatedWEBP)
or move it to a different node id, the client will still pick up the
output because :meth:`ComfyUIClient.extract_outputs` walks **all**
output keys, but the slot name ``FILENAME_PREFIX`` is currently set on
the assumption that ``VHS_VideoCombine`` accepts a ``filename_prefix``
input. If you switch nodes, update the workflow template.

### 3. LoRA loader expects a real file

The workflow has a ``LoraLoader`` node. When the LoRA name is empty,
``_substitute_slots`` sets it to ``"none"`` and strength to 0, but
ComfyUI will still try to look up ``none.safetensors`` and fail if
nothing matches. On Verda, the convention is to keep an empty/no-op
LoRA file at ``/mnt/models/loras/none.safetensors`` (zero-strength
applies a noop) — or remove the ``LoraLoader`` node from the template
entirely when you know you'll never use a LoRA.

Phase 3 can revisit by detecting the empty slot and surgically dropping
the ``LoraLoader`` node from the graph + re-wiring downstream inputs.
Out of scope for Phase 2.

### 4. Only one LoRA slot is templated

The base workflow has ``LORA_0_NAME`` / ``LORA_0_STRENGTH``. The Phase 2
``ai_metadata.lora_stack`` schema supports an arbitrary list, but only
the first entry is actually wired through. Multi-LoRA requires:
1. Adding more ``LoraLoader`` nodes to the workflow JSON (chained:
   each takes the previous one's model/clip outputs).
2. Adding more ``LORA_N_NAME``/``LORA_N_STRENGTH`` slots.
3. Updating ``BaseAIGenerator._build_slots`` to populate all N slots
   (looping over ``assembled.lora_stack``).

Documented here so Phase 3+ knows to expand the slot count when
training multiple channel LoRAs.

### 5. ``ComfyUI`` job timeout is wall-clock, not GPU-time

``BROLL_COMFYUI_JOB_TIMEOUT_SEC`` (default 600) caps total wait. A
slow instance (no spot capacity, queued behind another submission) can
blow through this even though the per-shot generation is fast. If you
batch 30 shots and the instance enqueues them, the 30th shot will
spend most of its budget waiting in queue. Either:
* Submit shots sequentially (current pipeline behaviour — one shot per
  ``run_shot`` call).
* Or raise the timeout for batch contexts.

### 6. Same-prompt-different-seed has no first-class flag

Today you'd vary the seed by setting ``_seed`` per shot or by changing
the prompt. There's no "give me three takes" mode. Phase 3 could add a
``--takes N`` flag to ``pipeline/broll.py`` that calls ``run_shot``
with ``_seed_salt=0,1,…,N-1``. Each take produces its own meta + log;
the orchestrator picks the best.

### 7. AI fallback in stock_first writes both cascade AND AI in the log

When stock_first falls back to AI, ``log.json`` ends up with both a
``cascade`` block and an ``ai`` block. The ``outcome`` key disambiguates
(``stock_first_ai_fallback``), but downstream consumers (Phase 4
attribution slate generator) should read ``outcome`` first to know
which provenance applies — not just look at which blocks are present.

### 8. ``VHS_VideoCombine`` returns mp4 with the file extension already
attached, so our ``.mp4`` target name and the upstream filename agree.
LTX/Wan can produce other containers (webm, animated webp) if you swap
the saver node. The asset_wrapper trusts the target filename for the
extension. If you change saver, also change the target naming convention
in ``pipeline/broll.py`` or add a normalization pass (Phase 4 work).

---

## Test counts

```
Offline:    176 tests pass.
Network:      5 pass / 2 skip on missing keys (Phase 1 sources, unchanged).

Phase-2 specific new tests:
  test_seed_strategy.py        — 8 tests
  test_prompt_assembly.py      — 9 tests
  test_ai_router.py            — 6 tests
  test_comfyui_client.py       — 5 tests (vs. the local HTTP mock)
  test_ai_sources.py           — 8 tests (full lifecycle, cache, retries)
  test_phase2_pipeline.py      — 8 tests (all 4 strategies, log shape)
```

Run offline only: ``pytest broll/tests/ -m "not network"``.

---

## Updated env vars

| Var                              | What it does                                    | Default            |
|----------------------------------|-------------------------------------------------|--------------------|
| ``BROLL_COMFYUI_URL``            | ComfyUI server URL                              | ``http://localhost:8188`` |
| ``BROLL_COMFYUI_JOB_TIMEOUT_SEC``| End-to-end wall-clock job timeout (s)           | 600                |
| ``BROLL_NO_AI_CACHE``            | ``1`` → disable the recipe cache                | (cache on)         |
| ``BROLL_VERIFIER_MODEL``         | Claude model id for the vision verifier         | ``claude-sonnet-4-6``|
| (existing vars from Phase 1 unchanged)                                                                |

The ``VERDA_CLIENT_ID`` / ``VERDA_CLIENT_SECRET`` env vars are NOT read
by the broll layer — they're for Terraform. The B-roll pipeline talks
to ComfyUI directly via HTTP.

---

## What's ready for Phase 3 to plug into

Phase 3 (verifier-driven LLM refinement loop) should:

1. **Read ``output/broll/<shot_id>.log.json``** after a
   ``reject_all`` or AI-failure outcome. The log already has the
   cascade candidates, verify reasons, and AI prompt/seed.

2. **Add ``broll/lib/refinement.py``** with an ``LLMClient`` protocol
   matching the one in :mod:`broll.lib.keyword_generator`. The
   refinement function takes:
   * The original shot spec.
   * The log of the previous attempt(s).
   * A target retry count.
   And returns a new (refined) shot spec OR a "give up, surface to
   human" signal.

3. **Wrap the existing ``run_shot``** with a refinement loop. The loop
   can sit either in ``pipeline/broll.py`` directly or in a new
   ``refinement.py`` orchestrator. Each iteration writes a new
   ``<shot_id>.attempt-<N>.log.json``; the final attempt's log is the
   one that becomes ``<shot_id>.log.json``.

4. **Re-verify AI outputs**. Today the AI path skips the verifier
   (gotcha #1). When Phase 3 lands, run the AI clip through
   :func:`verify.pick` exactly like the stock path; the verifier's
   ``verification_block()`` already supports populating the meta.

5. **Cap total compute**. Per AGENT.md: 2 LLM refinement iterations +
   3 AI generation retries per shot, max. Enforce that ceiling in
   ``refinement.py``; surface unresolved shots to
   ``failed_shots/<shot_id>.json`` with the full chain of attempts.

The schemas, asset wrapper, cache, rate limit, cascade, verify, AI
sources, and ComfyUI client should not need changes for Phase 3.
Workflow templates and prompt files might need iteration as the
refinement loop discovers new failure modes.

---

## Phase 2 exit criteria mapping

From ``plan(1).md``:

| Criterion | Status |
|---|---|
| ``broll/sources/ltx_video.py`` | ✅ |
| ``broll/sources/wan_video.py`` | ✅ |
| ``broll/lib/ai_router.py`` (LTX/Wan rule) | ✅ |
| ``broll/prompts/`` (templates + style tokens + LoRA stack) | ✅ |
| ``broll/lib/seed_strategy.py`` | ✅ |
| ComfyUI workflows in ``broll/comfyui_workflows/`` | ✅ |
| ``.meta.json`` captures full AI provenance (model, prompt, seed, LoRA, sampler, steps) | ✅ |
| Spot-pricing-tolerant (interrupt recovery) | ✅ — submit + poll retries, full-job resubmit |
| Cap per-shot retries (3) | ✅ — ``max_resubmits=2`` + initial submission = 3 attempts |
| Cache aggressively: same prompt + seed = same clip | ✅ — recipe-keyed cache, replay CLI for hot regen |
| **50 AI clips generated, consistent style, full meta** | 🔜 runtime measurement; tooling is in place |
| **Spot interruption recovery works (resume cleanly)** | ✅ in code; verify against real Verda by killing the instance mid-batch |

Good luck with Phase 3.

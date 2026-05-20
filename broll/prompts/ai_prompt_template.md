# AI prompt template

The B-roll layer builds an AI prompt in three layers:

1. **User intent** — verbatim from the shot spec's `intent` field. This is
   what the orchestrator's script-LLM produced and must not be paraphrased.
2. **Tone block** (optional) — appended when `shot_spec.tone` matches a
   `tone:<name>` block in `style_tokens.md`.
3. **Channel positive tokens** — the global "house style" block from
   `style_tokens.md` (`positive` fence).

The negative prompt is the union of:
* The global `negative` block from `style_tokens.md`.
* `shot_spec.negative_intent`, if present (verbatim, unchanged).

## Shape on the wire

The positive prompt sent to ComfyUI is, roughly:

    <intent>. <tone block>. <channel positive tokens>.

The negative prompt sent to ComfyUI is:

    <channel negative tokens>. <user negative_intent>.

Both strings are normalized (whitespace collapsed, trailing punctuation
deduped) before submission.

## Determinism

The exact strings produced for a given `(intent, tone, negative_intent,
model)` tuple are stable across runs — `prompt_assembly.build_prompt` is
pure. The seed strategy (`seed_strategy.seed_for`) hashes the produced
positive prompt, so the final ComfyUI seed only changes when one of the
input strings changes.

## LoRA stack

Default LoRA application is in `lora_stack.json`. Each entry is
`{"name": "<filename without extension>", "strength": <0..1>}`. Empty stack
is fine. The seed strategy includes the LoRA stack in its hash so swapping
LoRAs changes the seed (and therefore the cache key).

## Model-specific budgets

LTX-2.3 caps positive prompt at ~60 words (truncated mid-sentence in
practice). Wan 2.2 handles ~120. `prompt_assembly.build_prompt` enforces
per-model word caps in the channel-token block, not in the user's intent —
the intent is sacred.

## Where to edit

* Update aesthetic / negatives: `style_tokens.md`.
* Update default LoRAs: `lora_stack.json`.
* Update assembly logic: `broll/lib/prompt_assembly.py`.
* Per-shot override: shot spec `tone`, `negative_intent`, `_lora_stack`,
  `_seed`, `_seed_salt`.

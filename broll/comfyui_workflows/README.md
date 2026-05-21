# ComfyUI workflows (GeoPoAI)

## Layout

| Path | Format | Purpose |
|------|--------|---------|
| `*.json` (this directory) | **API** (`class_type` + `inputs`) | Submitted by `broll.sources.*` via `<<SLOT>>` substitution |
| `reference/` | **UI** (`nodes` + `links`) | Upstream examples from Lightricks / ComfyUI; not submitted directly |

## API templates

| File | Generator | Model weights (on `/mnt/models`) |
|------|-----------|----------------------------------|
| `ltx_2_3_t2v.json` | `ltx_video.LTXVideoGenerator` | `checkpoints/ltx/ltx-2.3-22b-dev-fp8.safetensors`, `text_encoders/gemma_3_12B_it_fp8_scaled.safetensors`, distilled + style LoRAs |
| `ltx_2_3_i2v.json` | manual / `flux_ltx` step 2 | same + `INPUT_IMAGE` in ComfyUI `input/` |
| `wan_2_2_t2v.json` | `wan_video.WanVideoGenerator` | `diffusion_models/wan2.2_t2v_{high,low}_noise_14B_fp8_scaled.safetensors` |
| `wan_2_2_i2v.json` | optional face-heavy I2V | `wan2.2_i2v_{high,low}_noise_14B_fp8_scaled.safetensors` |
| `flux_2_t2i.json` | `flux_image.FluxImageGenerator` | `flux2_dev_fp8mixed`, `flux2-vae`, `mistral_3_small_flux2_bf16` |
| `flux_ltx_i2v.json` | `flux_ltx_video` (after FLUX frame) | LTX I2V graph |

## Slot contract

Markers replaced by `broll.sources._ai_base._substitute_slots`:

- `<<PROMPT>>`, `<<NEGATIVE_PROMPT>>`, `<<SEED>>`, `<<STEPS>>`, `<<CFG>>`, `<<SAMPLER>>`
- `<<WIDTH>>`, `<<HEIGHT>>`, `<<NUM_FRAMES>>`, `<<FPS>>`
- `<<LORA_0_NAME>>`, `<<LORA_0_STRENGTH>>` (empty name → disabled)
- `<<FILENAME_PREFIX>>` — ComfyUI output subfolder/prefix
- `<<INPUT_IMAGE>>` — filename under ComfyUI `input/` (I2V / flux-ltx)

## Pipelines

- **Default video:** `ai_router.pick_ai_model` → `ltx-2.3` or `wan-2.2`
- **FLUX → LTX:** `shot_spec["_pipeline"] = "flux_ltx_i2v"` → `flux-ltx` source (FLUX PNG, upload, LTX I2V)

## Refresh reference JSON

```bash
./infra/scripts/fetch_reference_workflows.sh
```

## UI → API helper (experimental)

```bash
python -m broll.tools.workflow_ui_to_api broll/comfyui_workflows/reference/wan_2_2_t2v_14b.json
```

Prefer editing API templates directly after validating on a live ComfyUI box.

### Rebuild LTX T2V from reference

The LTX template is generated from `reference/ltx_2_3_t2v_i2v_single_stage_distilled.json` (CFGGuider + ManualSigmas path; no ClownSampler):

```bash
python -m broll.tools.build_ltx_t2v_workflow
```

#!/usr/bin/env bash
#
# download_models.sh — populate the persistent /mnt/models volume (idempotent).
# Invoked automatically from startup_scripts/comfyui_bootstrap.sh on first boot, or manually:
#   sudo -u ubuntu HF_TOKEN=hf_... bash /home/ubuntu/GeoPoAI/infra/download_models.sh
#
# Prereqs:
#   - /mnt/models mounted
#   - pip install -U "huggingface_hub[cli]"  (bootstrap installs this)
#   - HF_TOKEN or HUGGING_FACE_HUB_TOKEN set (gated repos need license accepted on HF web UI)
#
set -euo pipefail

MODELS="${GEOPOAI_MODELS_ROOT:-/mnt/models}"
MARKER="${MODELS}/.geopoai_download_complete"
MIN_BYTES_DEFAULT=50000000  # 50 MiB — catches truncated downloads

geopoai_human_bytes() {
  local sz="$1"
  if command -v numfmt >/dev/null 2>&1; then
    numfmt --to=iec-i --suffix=B "${sz}" 2>/dev/null || echo "${sz} B"
  else
    echo "${sz} B"
  fi
}

mkdir -p "${MODELS}"/{checkpoints/ltx,checkpoints/wan,checkpoints/flux,diffusion_models,vae,text_encoders,latent_upscale_models,loras,workflows,input,output}

if [[ -f "${MARKER}" ]]; then
  echo "[geopoai:download] marker present (${MARKER}); skipping downloads."
  exit 0
fi

HF_TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"
if [[ -z "${HF_TOKEN}" ]]; then
  echo "[geopoai:download] ERROR: set HF_TOKEN or HUGGING_FACE_HUB_TOKEN" >&2
  echo "  Accept licenses: Lightricks/LTX-2.3, Lightricks/LTX-2.3-fp8, Comfy-Org/* (see HF)" >&2
  exit 1
fi
export HF_TOKEN HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"

if ! command -v hf >/dev/null 2>&1; then
  python3 -m pip install --user -U "huggingface_hub[cli]"
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "=============================================="
echo " Downloading models to ${MODELS}"
echo " Expect 1–3 hours depending on bandwidth (~200+ GiB)."
echo "=============================================="

# hf download --local-dir DEST preserves repo paths (e.g. DEST/vae/foo.safetensors).
# ComfyUI expects flat names: DEST/foo.safetensors
geopoai_place_model_file() {
  local dest="$1" file="$2" base="$3"
  local dest_file="${dest}/${base}"
  local nested="${dest}/${file}"

  if [[ -f "${dest_file}" ]]; then
    return 0
  fi
  if [[ -f "${nested}" && "${nested}" != "${dest_file}" ]]; then
    echo "  [place] ${base}"
    mv -f "${nested}" "${dest_file}"
    return 0
  fi
  local found
  found="$(find "${dest}" -name "${base}" -type f ! -path "${dest_file}" -print -quit 2>/dev/null || true)"
  if [[ -n "${found}" ]]; then
    echo "  [place] ${base} (flatten nested layout)"
    mv -f "${found}" "${dest_file}"
    return 0
  fi
  return 1
}

dl() {
  local repo="$1" file="$2" dest="$3"
  local base dest_file
  base="$(basename "${file}")"
  dest_file="${dest}/${base}"

  if [[ -f "${dest_file}" ]]; then
    echo "  [skip] ${base}"
    return 0
  fi
  if geopoai_place_model_file "${dest}" "${file}" "${base}"; then
    return 0
  fi

  echo "  [get ] ${repo} :: ${file}"
  hf download "${repo}" "${file}" --local-dir "${dest}" --token "${HF_TOKEN}"
  geopoai_place_model_file "${dest}" "${file}" "${base}" || {
    echo "[geopoai:download] ERROR: ${base} not found under ${dest} after download" >&2
    return 1
  }
}

geopoai_flatten_all_known() {
  echo ""
  echo ">>> Flattening model paths for ComfyUI"
  geopoai_place_model_file "${MODELS}/checkpoints/ltx" "ltx-2.3-22b-dev-fp8.safetensors" "ltx-2.3-22b-dev-fp8.safetensors" || true
  geopoai_place_model_file "${MODELS}/vae" "vae/LTX23_video_vae_bf16.safetensors" "LTX23_video_vae_bf16.safetensors" || true
  geopoai_place_model_file "${MODELS}/vae" "vae/LTX23_audio_vae_bf16.safetensors" "LTX23_audio_vae_bf16.safetensors" || true
  geopoai_place_model_file "${MODELS}/vae" "vae/taeltx2_3.safetensors" "taeltx2_3.safetensors" || true
  geopoai_place_model_file "${MODELS}/text_encoders" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "ltx-2.3_text_projection_bf16.safetensors" || true
  geopoai_place_model_file "${MODELS}/text_encoders" "split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors" "gemma_3_12B_it_fp8_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/latent_upscale_models" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" || true
  geopoai_place_model_file "${MODELS}/loras" "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" || true
  geopoai_place_model_file "${MODELS}/loras" "LTX2.3_Soft_Enhance.safetensors" "LTX2.3_Soft_Enhance.safetensors" || true
  geopoai_place_model_file "${MODELS}/diffusion_models" "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/diffusion_models" "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/diffusion_models" "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/diffusion_models" "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/diffusion_models" "split_files/diffusion_models/flux2_dev_fp8mixed.safetensors" "flux2_dev_fp8mixed.safetensors" || true
  geopoai_place_model_file "${MODELS}/text_encoders" "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "umt5_xxl_fp8_e4m3fn_scaled.safetensors" || true
  geopoai_place_model_file "${MODELS}/vae" "split_files/vae/wan_2.1_vae.safetensors" "wan_2.1_vae.safetensors" || true
  geopoai_place_model_file "${MODELS}/vae" "split_files/vae/flux2-vae.safetensors" "flux2-vae.safetensors" || true
}

dl_min() {
  local path="$1" min_bytes="${2:-${MIN_BYTES_DEFAULT}}"
  if [[ ! -f "${path}" ]]; then
    echo "[geopoai:download] MISSING ${path}" >&2
    return 1
  fi
  local sz
  sz="$(stat -c%s "${path}")"
  if [[ "${sz}" -lt "${min_bytes}" ]]; then
    echo "[geopoai:download] TOO SMALL ${path} (${sz} bytes < ${min_bytes})" >&2
    return 1
  fi
  echo "  [ok  ] $(basename "${path}") ($(geopoai_human_bytes "${sz}"))"
}

# ── LTX 2.3 (fp8 checkpoint + Kijai VAE/text + Comfy-Org Gemma + upscaler + LoRA) ─
# HF layout (2026): fp8 weights live in Lightricks/LTX-2.3-fp8; VAE/text are not under
# Lightricks/LTX-2.3 root anymore — use Kijai/LTX2.3_comfy + Comfy-Org/ltx-2 repack.
echo ""
echo ">>> LTX-2.3"
LTX_MAIN="Lightricks/LTX-2.3"
LTX_FP8="Lightricks/LTX-2.3-fp8"
KIJAI_LTX="Kijai/LTX2.3_comfy"
LTX_COMFY_ORG="Comfy-Org/ltx-2"

dl "${LTX_FP8}" "ltx-2.3-22b-dev-fp8.safetensors" "${MODELS}/checkpoints/ltx"
dl "${KIJAI_LTX}" "vae/LTX23_video_vae_bf16.safetensors" "${MODELS}/vae"
dl "${KIJAI_LTX}" "vae/LTX23_audio_vae_bf16.safetensors" "${MODELS}/vae"
dl "${KIJAI_LTX}" "vae/taeltx2_3.safetensors" "${MODELS}/vae"
dl "${KIJAI_LTX}" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "${MODELS}/text_encoders"
dl "${LTX_COMFY_ORG}" "split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors" "${MODELS}/text_encoders"
dl "${LTX_MAIN}" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "${MODELS}/latent_upscale_models"
dl "${LTX_MAIN}" "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" "${MODELS}/loras"

# ── Wan 2.2 14B T2V + I2V (Comfy-Org repack; paths verified on HF) ───────────
echo ""
echo ">>> Wan 2.2 (14B T2V + I2V)"
WAN_REPO="Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
WAN_PREFIX="split_files"
dl "${WAN_REPO}" "${WAN_PREFIX}/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" "${MODELS}/diffusion_models"
dl "${WAN_REPO}" "${WAN_PREFIX}/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" "${MODELS}/diffusion_models"
dl "${WAN_REPO}" "${WAN_PREFIX}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" "${MODELS}/diffusion_models"
dl "${WAN_REPO}" "${WAN_PREFIX}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" "${MODELS}/diffusion_models"
dl "${WAN_REPO}" "${WAN_PREFIX}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "${MODELS}/text_encoders"
dl "${WAN_REPO}" "${WAN_PREFIX}/vae/wan_2.1_vae.safetensors" "${MODELS}/vae"

# ── FLUX.2 dev (Comfy-Org repack — avoids separate BFL gate for weights layout) ─
echo ""
echo ">>> FLUX.2 [dev] (Comfy-Org repack)"
FLUX_REPO="Comfy-Org/flux2-dev"
dl "${FLUX_REPO}" "split_files/diffusion_models/flux2_dev_fp8mixed.safetensors" "${MODELS}/diffusion_models"
dl "${FLUX_REPO}" "split_files/vae/flux2-vae.safetensors" "${MODELS}/vae"
dl "${FLUX_REPO}" "split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors" "${MODELS}/text_encoders"

# ── Style LoRA (in addition to LTX distilled LoRA above) ─────────────────────
echo ""
echo ">>> LoRAs (Soft Enhance)"
SOFT_LORA_REPO="vrgamedevgirl84/LTX_2.3_Soft_Enhance_Style_LoRa"
dl "${SOFT_LORA_REPO}" "LTX2.3_Soft_Enhance.safetensors" "${MODELS}/loras"

geopoai_flatten_all_known

echo ""
echo "=============================================="
echo " Verifying downloads"
echo "=============================================="
FAIL=0
dl_min "${MODELS}/checkpoints/ltx/ltx-2.3-22b-dev-fp8.safetensors" 15000000000 || FAIL=1
dl_min "${MODELS}/vae/LTX23_video_vae_bf16.safetensors" 100000000 || FAIL=1
dl_min "${MODELS}/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors" 5000000000 || FAIL=1
dl_min "${MODELS}/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" 5000000000 || FAIL=1
dl_min "${MODELS}/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors" 5000000000 || FAIL=1
dl_min "${MODELS}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" 5000000000 || FAIL=1
dl_min "${MODELS}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" 5000000000 || FAIL=1
dl_min "${MODELS}/diffusion_models/flux2_dev_fp8mixed.safetensors" 10000000000 || FAIL=1
dl_min "${MODELS}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" 3000000000 || FAIL=1
dl_min "${MODELS}/vae/wan_2.1_vae.safetensors" 50000000 || FAIL=1
dl_min "${MODELS}/vae/flux2-vae.safetensors" 50000000 || FAIL=1

LORA_FILE="$(find "${MODELS}/loras" -maxdepth 1 -name '*.safetensors' -print -quit)"
if [[ -z "${LORA_FILE}" ]]; then
  echo "[geopoai:download] MISSING LoRA in ${MODELS}/loras" >&2
  FAIL=1
else
  dl_min "${LORA_FILE}" 1000000 || FAIL=1
fi

if [[ "${FAIL}" -ne 0 ]]; then
  echo "[geopoai:download] verification failed — delete bad files and re-run" >&2
  exit 1
fi

date -Is >"${MARKER}"
echo ""
du -sh "${MODELS}"/checkpoints/* "${MODELS}"/diffusion_models "${MODELS}"/vae "${MODELS}"/text_encoders "${MODELS}"/loras 2>/dev/null || true
echo "[geopoai:download] complete — marker written: ${MARKER}"

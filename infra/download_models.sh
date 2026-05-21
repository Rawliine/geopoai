#!/usr/bin/env bash
#
# download_models.sh — populate the persistent /mnt/models volume (idempotent).
# Invoked automatically from comfyui_bootstrap.tftpl on first boot, or manually:
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

mkdir -p "${MODELS}"/{checkpoints/ltx,checkpoints/wan,checkpoints/flux,diffusion_models,vae,text_encoders,latent_upscale_models,loras,workflows,input,output}

if [[ -f "${MARKER}" ]]; then
  echo "[geopoai:download] marker present (${MARKER}); skipping downloads."
  exit 0
fi

HF_TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"
if [[ -z "${HF_TOKEN}" ]]; then
  echo "[geopoai:download] ERROR: set HF_TOKEN or HUGGING_FACE_HUB_TOKEN" >&2
  echo "  Accept licenses: Lightricks/LTX-2.3, black-forest-labs/FLUX.2-dev (if using upstream)" >&2
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

dl() {
  local repo="$1" file="$2" dest="$3"
  local base dest_file
  base="$(basename "${file}")"
  dest_file="${dest}/${base}"
  if [[ -f "${dest_file}" ]]; then
    echo "  [skip] ${base}"
    return 0
  fi
  echo "  [get ] ${repo} :: ${file}"
  hf download "${repo}" "${file}" --local-dir "${dest}" --token "${HF_TOKEN}"
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
  echo "  [ok  ] $(basename "${path}") ($(numfmt --to=iec-i --suffix=B "${sz}" 2>/dev/null || echo "${sz} B"))"
}

# ── LTX 2.3 (dev fp8 + VAE + Gemma + upscaler + refine LoRA) ─────────────────
echo ""
echo ">>> LTX-2.3"
dl "Lightricks/LTX-2.3" "ltx-2.3-22b-dev-fp8.safetensors" "${MODELS}/checkpoints/ltx"
dl "Lightricks/LTX-2.3" "vae/ltx-2.3-22b-dev_video_vae.safetensors" "${MODELS}/vae"
dl "Lightricks/LTX-2.3" "vae/ltx-2.3-22b-dev_audio_vae.safetensors" "${MODELS}/vae"
dl "Kijai/LTX2.3_comfy" "taeltx2_3.safetensors" "${MODELS}/vae"
dl "Lightricks/LTX-2.3" "text_encoders/ltx-2.3-22b-dev_embeddings_connectors.safetensors" "${MODELS}/text_encoders"
dl "unsloth/gemma-3-12b-it-qat-GGUF" "gemma-3-12b-it-qat-UD-Q4_K_XL.gguf" "${MODELS}/text_encoders"
dl "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.0.safetensors" "${MODELS}/latent_upscale_models"
dl "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "${MODELS}/loras"

# ── Wan 2.2 14B T2V + I2V (Comfy-Org repack) ─────────────────────────────────
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

# ── Style LoRA ────────────────────────────────────────────────────────────────
echo ""
echo ">>> LoRAs"
# Repo may ship one or more .safetensors; download all into loras/
hf download "vrgamedevgirl84/LTX_2.3_Soft_Enhance_Style_LoRa" \
  --include "*.safetensors" \
  --local-dir "${MODELS}/loras" \
  --token "${HF_TOKEN}"

echo ""
echo "=============================================="
echo " Verifying downloads"
echo "=============================================="
FAIL=0
dl_min "${MODELS}/checkpoints/ltx/ltx-2.3-22b-dev-fp8.safetensors" 15000000000 || FAIL=1
dl_min "${MODELS}/vae/ltx-2.3-22b-dev_video_vae.safetensors" 100000000 || FAIL=1
dl_min "${MODELS}/text_encoders/gemma-3-12b-it-qat-UD-Q4_K_XL.gguf" 5000000000 || FAIL=1
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

#!/usr/bin/env bash
# Re-download upstream ComfyUI workflow JSON into broll/comfyui_workflows/reference/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REF="${ROOT}/broll/comfyui_workflows/reference"
mkdir -p "${REF}"

fetch() {
  local url="$1" out="$2"
  echo "GET ${url}"
  curl -fsSL "${url}" -o "${out}"
}

fetch \
  "https://raw.githubusercontent.com/Lightricks/ComfyUI-LTXVideo/master/example_workflows/2.3/LTX-2.3_T2V_I2V_Single_Stage_Distilled_Full.json" \
  "${REF}/ltx_2_3_t2v_i2v_single_stage_distilled.json"

fetch \
  "https://raw.githubusercontent.com/comfyanonymous/ComfyUI_examples/master/wan22/text_to_video_wan22_14B.json" \
  "${REF}/wan_2_2_t2v_14b.json"

fetch \
  "https://raw.githubusercontent.com/comfyanonymous/ComfyUI_examples/master/wan22/image_to_video_wan22_14B.json" \
  "${REF}/wan_2_2_i2v_14b.json"

# FLUX.2 — try Comfy-Org workflow templates, then ComfyUI script_examples
if ! fetch "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/flux2/flux2_dev_t2i.json" "${REF}/flux_2_t2i.json" 2>/dev/null; then
  fetch "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/script_examples/flux2_text_to_image.json" "${REF}/flux_2_t2i.json" || true
fi

cat > "${REF}/SOURCES.txt" <<'EOF'
ltx_2_3_t2v_i2v_single_stage_distilled.json — Lightricks/ComfyUI-LTXVideo example_workflows/2.3
wan_2_2_t2v_14b.json — comfyanonymous/ComfyUI_examples wan22
wan_2_2_i2v_14b.json — comfyanonymous/ComfyUI_examples wan22
flux_2_t2i.json — Comfy-Org/workflow_templates or ComfyUI script_examples (best effort)
EOF

echo "Done. Files in ${REF}"

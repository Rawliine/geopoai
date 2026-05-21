#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# repair_comfyui_setup.sh — re-run ComfyUI bootstrap on the live setup VM over SSH.
# Use when first-boot died (e.g. old startup script with bad apt packages).
#
# Usage:
#   cd infra
#   ./repair_comfyui_setup.sh setup-001
#   ./repair_comfyui_setup.sh setup-001 --watch   # repair then tail bootstrap log
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/geopoai_common.sh
source "${INFRA_DIR}/lib/geopoai_common.sh"

RUN_ID="${1:-}"
shift || true

WATCH=false
for arg in "$@"; do
  case "${arg}" in
    --watch) WATCH=true ;;
    *) echo "unknown arg: ${arg}" >&2; exit 1 ;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 <run_id> [--watch]" >&2
  exit 1
fi

cd "${INFRA_DIR}"
geopoai_load_dotenv

export GEOPOAI_TF_REFRESH_ARGS="-var=run_id=${RUN_ID} -var-file=workloads/comfyui.tfvars"

GEOPOAI_GIT_REPO="${GEOPOAI_GIT_REPO:-$(terraform console -json <<< 'var.geopoai_git_repo' 2>/dev/null | tr -d '"' || echo "https://github.com/Rawliine/geopoai.git")}"
COMFYUI_LISTEN_PORT="${COMFYUI_LISTEN_PORT:-$(terraform console -json <<< 'var.comfyui_listen_port' 2>/dev/null | tr -d '"' || echo "8188")}"
export GEOPOAI_SSH_PUBLIC_KEY_LINE="$(geopoai_ssh_public_key_line)"
export GEOPOAI_GIT_REPO
export COMFYUI_LISTEN_PORT
export HF_TOKEN="${TF_VAR_huggingface_token:-${HF_TOKEN:-}}"
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"

chmod +x "${INFRA_DIR}/verda_ssh.sh" "${INFRA_DIR}/wait_for_instance_ip.sh" 2>/dev/null || true

echo "[geopoai] repairing bootstrap on setup VM (run_id=${RUN_ID})..." >&2
"${INFRA_DIR}/verda_ssh.sh" -- env \
  GEOPOAI_GIT_REPO="${GEOPOAI_GIT_REPO}" \
  GEOPOAI_SSH_PUBLIC_KEY_LINE="${GEOPOAI_SSH_PUBLIC_KEY_LINE}" \
  COMFYUI_LISTEN_PORT="${COMFYUI_LISTEN_PORT}" \
  HF_TOKEN="${HF_TOKEN}" \
  HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
  bash -s < "${INFRA_DIR}/scripts/resume_bootstrap_on_vm.sh"

if [[ "${WATCH}" == true ]]; then
  exec "${INFRA_DIR}/verda_ssh.sh" -- tail -f /var/log/geopoai-bootstrap.log
fi

echo "[geopoai] repair finished — check /var/log/geopoai-bootstrap-resume.log on the VM" >&2

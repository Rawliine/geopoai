#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# download_models_on_vm.sh — run download_models.sh on the setup VM (no full repair).
# Use when repair/bootstrap finished but models were skipped (e.g. old GEOPOAI_GIT_REPO check).
#
#   cd infra && set -a && source ../.env && set +a
#   ./download_models_on_vm.sh setup-001
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/geopoai_common.sh
source "${INFRA_DIR}/lib/geopoai_common.sh"

RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 <run_id>" >&2
  exit 1
fi

cd "${INFRA_DIR}"
geopoai_load_dotenv
export GEOPOAI_TF_REFRESH_ARGS="-var=run_id=${RUN_ID} -var-file=workloads/comfyui.tfvars"

export HF_TOKEN="${TF_VAR_huggingface_token:-${HF_TOKEN:-}}"
if [[ -z "${HF_TOKEN}" ]]; then
  echo "error: set TF_VAR_huggingface_token in ../.env" >&2
  exit 1
fi

SSH_IDENTITY="$(geopoai_resolve_ssh_private_key)" || exit 1
IP="$(geopoai_wait_for_instance_ip)"

echo "[geopoai] syncing infra + broll to VM..." >&2
geopoai_rsync_repo_to_vm "${IP}" "${SSH_IDENTITY}" root

echo "[geopoai] starting download_models.sh on VM (hours)..." >&2
# ubuntu may not be in sudoers on Verda images — run as root; use ComfyUI venv for `hf` CLI.
GEOPOAI_SSH_USER=root "${INFRA_DIR}/verda_ssh.sh" -- bash -c "
  set -euo pipefail
  export HF_TOKEN='${HF_TOKEN}'
  export HUGGING_FACE_HUB_TOKEN='${HF_TOKEN}'
  export PATH=/home/ubuntu/ComfyUI/.venv/bin:\${HOME}/.local/bin:\${PATH}
  if [[ -x /home/ubuntu/ComfyUI/.venv/bin/python ]]; then
    source /home/ubuntu/ComfyUI/.venv/bin/activate
  fi
  bash /home/ubuntu/GeoPoAI/infra/download_models.sh
"

echo "[geopoai] done — check: ./verda_ssh.sh -- test -f /mnt/models/.geopoai_download_complete && echo ok"

#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# repair_comfyui_setup.sh — re-run ComfyUI bootstrap on the live setup VM over SSH.
# Syncs your local GeoPoAI checkout to the VM (no GitHub HTTPS auth on the server).
#
# Usage:
#   cd infra
#   ./repair_comfyui_setup.sh setup-001
#   ./repair_comfyui_setup.sh setup-001 --watch
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

# Pass through extra -var-file flags (e.g. fin03/a6000) via GEOPOAI_TF_REFRESH_ARGS if set.
export GEOPOAI_TF_REFRESH_ARGS="${GEOPOAI_TF_REFRESH_ARGS:--var=run_id=${RUN_ID} -var-file=workloads/comfyui.tfvars}"

COMFYUI_LISTEN_PORT="${COMFYUI_LISTEN_PORT:-$(terraform console -json <<< 'var.comfyui_listen_port' 2>/dev/null | tr -d '"' || echo "8188")}"
export GEOPOAI_SSH_PUBLIC_KEY_LINE="$(geopoai_ssh_public_key_line)"
export COMFYUI_LISTEN_PORT
export HF_TOKEN="${TF_VAR_huggingface_token:-${HF_TOKEN:-}}"
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
export GEOPOAI_REPO_PRELOADED=1

chmod +x "${INFRA_DIR}/verda_ssh.sh" "${INFRA_DIR}/wait_for_instance_ip.sh" 2>/dev/null || true

SSH_IDENTITY="$(geopoai_resolve_ssh_private_key)" || {
  echo "error: no SSH private key found" >&2
  exit 1
}

echo "[geopoai] waiting for instance_ip..." >&2
IP="$(geopoai_wait_for_instance_ip)"

echo "[geopoai] syncing local repo to VM (run_id=${RUN_ID})..." >&2
# root@ — ubuntu@ may not have authorized_keys until after resume installs SSH key
geopoai_rsync_repo_to_vm "${IP}" "${SSH_IDENTITY}" root

echo "[geopoai] running bootstrap repair on VM..." >&2
GEOPOAI_GIT_REPO="${GEOPOAI_GIT_REPO:-$(terraform console -json <<< 'var.geopoai_git_repo' 2>/dev/null | tr -d '"' || true)}"

{
  printf 'export GEOPOAI_REPO_PRELOADED=%q\n' "1"
  printf 'export GEOPOAI_GIT_REPO=%q\n' "${GEOPOAI_GIT_REPO}"
  printf 'export GEOPOAI_SSH_PUBLIC_KEY_LINE=%q\n' "${GEOPOAI_SSH_PUBLIC_KEY_LINE}"
  printf 'export COMFYUI_LISTEN_PORT=%q\n' "${COMFYUI_LISTEN_PORT}"
  printf 'export HF_TOKEN=%q\n' "${HF_TOKEN}"
  printf 'export HUGGING_FACE_HUB_TOKEN=%q\n' "${HF_TOKEN}"
  printf 'export GEOPOAI_MAX_SESSION_HOURS=%q\n' "${GEOPOAI_MAX_SESSION_HOURS:-6}"
  printf 'export VERDA_CLIENT_ID=%q\n' "${VERDA_CLIENT_ID:-${TF_VAR_verda_client_id:-}}"
  printf 'export VERDA_CLIENT_SECRET=%q\n' "${VERDA_CLIENT_SECRET:-${TF_VAR_verda_client_secret:-}}"
  cat "${INFRA_DIR}/scripts/resume_bootstrap_on_vm.sh"
} | GEOPOAI_SSH_USER=root "${INFRA_DIR}/verda_ssh.sh" -- bash -s

if [[ "${WATCH}" == true ]]; then
  exec "${INFRA_DIR}/verda_ssh.sh" -- tail -f /var/log/geopoai-bootstrap.log
fi

echo "[geopoai] repair finished — check /var/log/geopoai-bootstrap-resume.log on the VM" >&2

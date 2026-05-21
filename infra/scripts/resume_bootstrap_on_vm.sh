#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Idempotent ComfyUI bootstrap repair on a Verda VM (after a partial first boot).
# Invoked automatically by repair_comfyui_setup.sh over SSH — not run by hand unless debugging.
#
# Required env (set by repair_comfyui_setup.sh or Terraform startup script):
#   GEOPOAI_SSH_PUBLIC_KEY_LINE, GEOPOAI_GIT_REPO, COMFYUI_LISTEN_PORT
#   HF_TOKEN or HUGGING_FACE_HUB_TOKEN (for model download)
# -----------------------------------------------------------------------------
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
exec > >(tee -a /var/log/geopoai-bootstrap-resume.log) 2>&1

echo "[geopoai:resume] start $(date -Is)"

GEOPOAI_REPO="${GEOPOAI_REPO:-/home/ubuntu/GeoPoAI}"
STARTUP="${GEOPOAI_REPO}/infra/startup_scripts"

geopoai_source_libs_from_repo() {
  if [[ ! -d "${STARTUP}" ]]; then
    echo "[geopoai:resume] ERROR: ${STARTUP} missing — set GEOPOAI_GIT_REPO and re-run repair" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${STARTUP}/lib_user.sh"
  # shellcheck source=/dev/null
  source "${STARTUP}/lib_mount.sh"
  # shellcheck source=/dev/null
  source "${STARTUP}/lib_ssh_access.sh"
  # shellcheck source=/dev/null
  source "${STARTUP}/lib_apt_comfyui.sh"
}

if [[ -d "${GEOPOAI_REPO}/infra/startup_scripts" ]]; then
  echo "[geopoai:resume] using repo at ${GEOPOAI_REPO} (pre-synced or existing)" >&2
elif [[ "${GEOPOAI_REPO_PRELOADED:-}" == "1" ]]; then
  echo "[geopoai:resume] ERROR: GEOPOAI_REPO_PRELOADED=1 but ${GEOPOAI_REPO} is missing — re-run repair from your laptop" >&2
  exit 1
elif [[ ! -d "${GEOPOAI_REPO}/.git" ]]; then
  if [[ -z "${GEOPOAI_GIT_REPO:-}" ]]; then
    GEOPOAI_GIT_REPO="${GEOPOAI_GIT_REPO_DEFAULT:-https://github.com/Rawliine/geopoai.git}"
  fi
  echo "[geopoai:resume] cloning GeoPoAI from ${GEOPOAI_GIT_REPO}" >&2
  mkdir -p "$(dirname "${GEOPOAI_REPO}")"
  if ! id -u ubuntu &>/dev/null 2>&1; then
    useradd -m -s /bin/bash -U ubuntu
  fi
  if ! sudo -u ubuntu env GIT_TERMINAL_PROMPT=0 git clone --depth 1 "${GEOPOAI_GIT_REPO}" "${GEOPOAI_REPO}"; then
    echo "[geopoai:resume] git clone failed (private repo or bad URL). From your laptop run:" >&2
    echo "  cd infra && ./repair_comfyui_setup.sh <run_id>" >&2
    exit 1
  fi
fi

geopoai_source_libs_from_repo

geopoai_ensure_login_user
geopoai_mount_models_volume

if [[ -n "${GEOPOAI_SSH_PUBLIC_KEY_LINE:-}" ]]; then
  geopoai_install_ssh_authorized_key
fi

# shellcheck source=/dev/null
source "${STARTUP}/comfyui_bootstrap.sh"

echo "[geopoai:resume] finished OK $(date -Is)"

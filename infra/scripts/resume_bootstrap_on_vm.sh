#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Run ON THE VERDA VM as root when first-boot bootstrap died early (no ubuntu user).
# Creates ubuntu, fixes /mnt/models ownership, re-runs GeoPoAI bootstrap body.
#
#   curl -fsSL ... | bash   # or scp this file and: bash resume_bootstrap_on_vm.sh
# -----------------------------------------------------------------------------
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
exec > >(tee -a /var/log/geopoai-bootstrap-resume.log) 2>&1

echo "[geopoai:resume] start $(date -Is)"

if ! id -u ubuntu &>/dev/null 2>&1; then
  echo "[geopoai:resume] creating ubuntu user"
  useradd -m -s /bin/bash -U ubuntu
fi

if [[ -d /mnt/models ]]; then
  chown -R ubuntu:ubuntu /mnt/models
fi

# Re-run assembled bootstrap from repo if present; else clone and run download only
if [[ -x /root/GeoPoAI/infra/download_models.sh ]]; then
  GEOPOAI_DIR=/root/GeoPoAI
elif [[ -x /home/ubuntu/GeoPoAI/infra/download_models.sh ]]; then
  GEOPOAI_DIR=/home/ubuntu/GeoPoAI
else
  echo "[geopoai:resume] cloning GeoPoAI (set GEOPOAI_GIT_REPO to override)"
  GEOPOAI_GIT_REPO="${GEOPOAI_GIT_REPO:-https://github.com/Rawliine/geopoai.git}"
  GEOPOAI_DIR=/home/ubuntu/GeoPoAI
  sudo -u ubuntu git clone --depth 1 "${GEOPOAI_GIT_REPO}" "${GEOPOAI_DIR}" || true
fi

if [[ -f "${GEOPOAI_DIR}/infra/startup_scripts/comfyui_bootstrap.tftpl" ]]; then
  echo "[geopoai:resume] run full comfyui install via existing repo scripts — install ComfyUI manually if missing"
fi

if [[ -x "${GEOPOAI_DIR}/infra/download_models.sh" ]] && [[ ! -f /mnt/models/.geopoai_download_complete ]]; then
  echo "[geopoai:resume] running download_models.sh"
  export HF_TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"
  if [[ -z "${HF_TOKEN}" ]]; then
    echo "[geopoai:resume] ERROR: export HF_TOKEN=hf_... before running" >&2
    exit 1
  fi
  sudo -u ubuntu env HF_TOKEN="${HF_TOKEN}" HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
    bash "${GEOPOAI_DIR}/infra/download_models.sh"
fi

echo "[geopoai:resume] done $(date -Is)"

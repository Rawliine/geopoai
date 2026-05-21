# -----------------------------------------------------------------------------
# ComfyUI workload — full stack (ComfyUI + custom nodes + model download + tmux).
# Environment (set by Terraform locals or repair_comfyui_setup.sh):
#   GEOPOAI_GIT_REPO, COMFYUI_LISTEN_PORT, HF_TOKEN / HUGGING_FACE_HUB_TOKEN
# -----------------------------------------------------------------------------

geopoai_apt_install_comfyui_packages

COMFYUI_LISTEN_PORT="${COMFYUI_LISTEN_PORT:-8188}"
HF_TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"
if [[ -n "${HF_TOKEN}" ]]; then
  export HF_TOKEN HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
fi

geopoai_clone_repo() {
  local url="$1" dest="$2" branch="${3:-}"
  if [[ -d "${dest}/.git" ]]; then
    echo "[geopoai:comfyui] ${dest} exists; git pull" >&2
    sudo -u ubuntu git -C "${dest}" pull --ff-only || true
    return 0
  fi
  if [[ -n "${branch}" ]]; then
    sudo -u ubuntu git clone --depth 1 --branch "${branch}" "${url}" "${dest}"
  else
    sudo -u ubuntu git clone --depth 1 "${url}" "${dest}"
  fi
}

geopoai_install_custom_node() {
  local url="$1" dest_name="$2"
  local dest="/home/ubuntu/ComfyUI/custom_nodes/${dest_name}"
  geopoai_clone_repo "${url}" "${dest}"
  if [[ -f "${dest}/requirements.txt" ]]; then
    sudo -u ubuntu bash -c "
      set -euo pipefail
      cd '${dest}'
      source /home/ubuntu/ComfyUI/.venv/bin/activate
      python -m pip install --no-cache-dir -r requirements.txt
    "
  fi
}

sudo -u ubuntu bash <<'EOSU_ROOT'
set -euo pipefail
cd /home/ubuntu

if [[ ! -d ComfyUI ]]; then
  echo "[geopoai:comfyui] cloning ComfyUI"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
fi

cd ComfyUI
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install --no-cache-dir -r requirements.txt
python -m pip install --no-cache-dir -U "huggingface_hub[cli]"
EOSU_ROOT

geopoai_install_custom_node "https://github.com/Lightricks/ComfyUI-LTXVideo.git" "ComfyUI-LTXVideo"
geopoai_install_custom_node "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" "ComfyUI-VideoHelperSuite"
geopoai_install_custom_node "https://github.com/city96/ComfyUI-GGUF.git" "ComfyUI-GGUF"
geopoai_install_custom_node "https://github.com/kijai/ComfyUI-KJNodes.git" "ComfyUI-KJNodes"

GEOPOAI_DIR="/home/ubuntu/GeoPoAI"
if [[ -x "${GEOPOAI_DIR}/infra/download_models.sh" ]]; then
  echo "[geopoai:comfyui] using GeoPoAI at ${GEOPOAI_DIR} (local/rsync/pre-cloned)" >&2
elif [[ -n "${GEOPOAI_GIT_REPO:-}" ]]; then
  if [[ ! -d "${GEOPOAI_DIR}/.git" ]]; then
    echo "[geopoai:comfyui] cloning GeoPoAI from ${GEOPOAI_GIT_REPO}" >&2
    sudo -u ubuntu git clone --depth 1 "${GEOPOAI_GIT_REPO}" "${GEOPOAI_DIR}"
  else
    sudo -u ubuntu git -C "${GEOPOAI_DIR}" pull --ff-only || true
  fi
  chmod +x "${GEOPOAI_DIR}/infra/download_models.sh" 2>/dev/null || true
else
  echo "[geopoai:comfyui] WARNING: no GeoPoAI repo at ${GEOPOAI_DIR} and GEOPOAI_GIT_REPO unset — skipping downloads/workflows" >&2
  GEOPOAI_DIR=""
fi

echo "[geopoai:comfyui] wiring ComfyUI model dirs -> /mnt/models" >&2
sudo -u ubuntu bash <<'EOSU_LINK'
set -euo pipefail
cd /home/ubuntu/ComfyUI/models
for d in checkpoints diffusion_models vae text_encoders latent_upscale_models loras input output user; do
  rm -rf "${d}" || true
  ln -sfn "/mnt/models/${d}" "${d}"
done
mkdir -p /home/ubuntu/ComfyUI/user/default
EOSU_LINK

if [[ -n "${GEOPOAI_DIR}" && -x "${GEOPOAI_DIR}/infra/download_models.sh" ]]; then
  if [[ ! -f /mnt/models/.geopoai_download_complete ]]; then
    echo "[geopoai:comfyui] running download_models.sh (long — see /var/log/geopoai-bootstrap.log)" >&2
    if [[ -z "${HF_TOKEN:-}" ]]; then
      echo "[geopoai:comfyui] ERROR: HF_TOKEN not set — cannot download models" >&2
      exit 1
    fi
    sudo -u ubuntu env HF_TOKEN="${HF_TOKEN}" HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
      bash "${GEOPOAI_DIR}/infra/download_models.sh"
  else
    echo "[geopoai:comfyui] models already on volume (marker present)" >&2
  fi
else
  echo "[geopoai:comfyui] skip model download (no GeoPoAI repo or script)" >&2
fi

if [[ -n "${GEOPOAI_DIR}" && -d "${GEOPOAI_DIR}/broll/comfyui_workflows" ]]; then
  rsync -a "${GEOPOAI_DIR}/broll/comfyui_workflows/" /mnt/models/workflows/
  ln -sfn /mnt/models/workflows /home/ubuntu/ComfyUI/user/default/workflows
fi

echo "[geopoai:comfyui] starting ComfyUI in tmux (session: comfyui)" >&2
sudo -u ubuntu bash <<EOSU2
set -euo pipefail
cd /home/ubuntu/ComfyUI
source .venv/bin/activate
tmux has-session -t comfyui 2>/dev/null && tmux kill-session -t comfyui || true
tmux new-session -d -s comfyui "cd /home/ubuntu/ComfyUI && . .venv/bin/activate && exec python main.py --listen 0.0.0.0 --port ${COMFYUI_LISTEN_PORT}"
EOSU2

echo "[geopoai:comfyui] ComfyUI on 0.0.0.0:${COMFYUI_LISTEN_PORT}" >&2

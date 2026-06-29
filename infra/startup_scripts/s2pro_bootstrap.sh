# -----------------------------------------------------------------------------
# s2pro_bootstrap.sh — Fish Audio S2-Pro TTS API server (workload=s2pro).
# -----------------------------------------------------------------------------
# Self-contained: installs its own system deps, clones fish-speech, installs via
# uv (Python 3.12), downloads `fishaudio/s2-pro` to the persistent /mnt/models
# volume, and serves the /v1/tts API in a tmux session. Idempotent — skips the
# download when weights are already on the volume.
#
# It does NOT touch the ComfyUI/LTX bootstrap. The only things shared are the
# persistent /mnt/models volume (own checkpoints/s2-pro subdir) and the common
# user/mount/ssh/deadman libs prepended by locals.tf.
#
# Env (exported by locals.tf for workload=s2pro): HF_TOKEN, HUGGING_FACE_HUB_TOKEN,
# S2PRO_LISTEN_PORT.
#
# Gated repo: accept the Fish Audio Research License (NON-COMMERCIAL) at
# huggingface.co/fishaudio/s2-pro before first boot, or the download 401s.
# -----------------------------------------------------------------------------

MODELS="${GEOPOAI_MODELS_ROOT:-/mnt/models}"
PORT="${S2PRO_LISTEN_PORT:-8888}"
RUN_USER="ubuntu"
APP_DIR="/home/${RUN_USER}/fish-speech"
CKPT="${MODELS}/checkpoints/s2-pro"
UV="/home/${RUN_USER}/.local/bin/uv"

echo "[geopoai:s2pro] start — port=${PORT} ckpt=${CKPT}"

# 1) System dependencies (fish-speech runtime).
apt-get update -y
apt-get install -y --no-install-recommends \
  git ffmpeg portaudio19-dev libsox-dev tmux curl ca-certificates

# 2) uv (manages Python 3.12 + the venv) for the run user.
if [[ ! -x "${UV}" ]]; then
  sudo -u "${RUN_USER}" -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

# 3) Clone (or fast-forward) fish-speech.
if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "${RUN_USER}" -H git -C "${APP_DIR}" pull --ff-only || true
else
  sudo -u "${RUN_USER}" -H git clone --depth 1 https://github.com/fishaudio/fish-speech.git "${APP_DIR}"
fi

# 4) Install the GPU build (CUDA 12.9 wheels) + the HF CLI.
sudo -u "${RUN_USER}" -H bash -lc "cd '${APP_DIR}' && '${UV}' sync --python 3.12 --extra cu129"
sudo -u "${RUN_USER}" -H bash -lc "cd '${APP_DIR}' && '${UV}' pip install -U 'huggingface_hub[cli]'"

# 5) Download weights to the persistent volume (idempotent).
mkdir -p "${CKPT}"
chown -R "${RUN_USER}:${RUN_USER}" "${CKPT}"
if [[ -z "$(ls -A "${CKPT}" 2>/dev/null)" ]]; then
  if [[ -z "${HF_TOKEN:-}" ]]; then
    echo "[geopoai:s2pro] ERROR: HF_TOKEN unset and weights absent — set TF_VAR_huggingface_token" >&2
    echo "  and accept the license at huggingface.co/fishaudio/s2-pro first." >&2
    exit 1
  fi
  sudo -u "${RUN_USER}" -H env HF_TOKEN="${HF_TOKEN}" HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
    bash -lc "cd '${APP_DIR}' && '${UV}' run hf download fishaudio/s2-pro --local-dir '${CKPT}'"
else
  echo "[geopoai:s2pro] weights already present at ${CKPT}; skipping download."
fi

# 6) Link weights into the repo + serve the API in a tmux session.
sudo -u "${RUN_USER}" -H bash -lc "mkdir -p '${APP_DIR}/checkpoints' && ln -sfn '${CKPT}' '${APP_DIR}/checkpoints/s2-pro'"
sudo -u "${RUN_USER}" -H tmux kill-session -t s2pro 2>/dev/null || true
sudo -u "${RUN_USER}" -H tmux new-session -d -s s2pro \
  "cd '${APP_DIR}' && '${UV}' run python tools/api_server.py \
     --llama-checkpoint-path checkpoints/s2-pro \
     --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
     --listen 0.0.0.0:${PORT} --half --compile \
     2>&1 | tee -a /home/${RUN_USER}/s2pro_server.log"

echo "[geopoai:s2pro] api_server launching on :${PORT} (tmux 's2pro'); model=${CKPT}"

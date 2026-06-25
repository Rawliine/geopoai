# -----------------------------------------------------------------------------
# LoRA training workload body (runs AFTER lib_mount.sh + geopoai_mount_models_volume)
# -----------------------------------------------------------------------------
# This intentionally does NOT install ai-toolkit / kohya for you: those projects
# move quickly and you may want a specific commit. After SSH:
#   cd /mnt/models
#   git clone https://github.com/ostris/ai-toolkit.git
#   cd ai-toolkit && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
#
# Put datasets under /mnt/models/training_sets/<name>/ so they survive destroys.
# Write outputs to /mnt/models/loras/ so the next ComfyUI instance picks them up.
# -----------------------------------------------------------------------------

echo "[geopoai:lora] installing training-friendly OS packages" >&2
apt-get install -y --no-install-recommends \
  git \
  curl \
  ca-certificates \
  tmux \
  nvtop \
  rsync \
  build-essential \
  python3 \
  python3-venv \
  python3-pip \
  jq

echo "[geopoai:lora] ready. Next steps (from infra/README.md):" >&2
echo "  - tmux new -s train" >&2
echo "  - install ai-toolkit or kohya under /mnt/models or /home/ubuntu" >&2
echo "  - keep checkpoints on /mnt/models (spot-safe)" >&2

geopoai_install_deadman_cron

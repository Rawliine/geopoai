# -----------------------------------------------------------------------------
# Blender batch render workload body (runs AFTER lib_mount.sh + mount)
# -----------------------------------------------------------------------------
# Typical session (see README.md):
#   rsync -avz ./characters ubuntu@IP:~/GeoPoAI/characters
#   ssh …
#   blender --background your.blend -a   # or -f 1..240 etc.
#
# Outputs can land in /mnt/models/output if you want them on the persistent
# volume, or in /home/ubuntu/outputs for quick pulls before destroy.
# -----------------------------------------------------------------------------

echo "[geopoai:blender] installing Blender + helpers" >&2
apt-get install -y --no-install-recommends \
  blender \
  tmux \
  rsync \
  git \
  curl \
  ca-certificates \
  jq

install -d -o ubuntu -g ubuntu /home/ubuntu/outputs /home/ubuntu/renders /home/ubuntu/GeoPoAI

echo "[geopoai:blender] Blender installed: $(command -v blender)" >&2
blender --version || true

echo "[geopoai:blender] ready. Sync .blend files in, render to ~/outputs or /mnt/models/output." >&2

geopoai_install_deadman_cron

# -----------------------------------------------------------------------------
# geopoai_apt_install_comfyui_packages — OS deps for ComfyUI bootstrap (idempotent).
# Note: numfmt is not an apt package on Ubuntu; it ships in coreutils (already installed).
# -----------------------------------------------------------------------------

geopoai_apt_install_comfyui_packages() {
  echo "[geopoai:comfyui] installing OS packages" >&2
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    tmux \
    jq \
    rsync \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    coreutils
}

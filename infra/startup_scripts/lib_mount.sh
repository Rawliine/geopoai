# -----------------------------------------------------------------------------
# Shared helpers: discover the first non-root block device and mount /mnt/models
# -----------------------------------------------------------------------------
# Verda attaches the persistent volume as an additional block device. Cloud
# images vary (NVMe vs virtio), so we:
#   1) Resolve the disk backing "/" via lsblk PKNAME
#   2) Pick the first block device (/dev/nvme*n1, /dev/vd?, /dev/sd?) that is
#      not that root disk
#   3) If it has no ext4 filesystem, create one with label geopoai-models
#   4) Mount at /mnt/models and add an fstab entry (LABEL=, nofail)
#
# If no secondary disk exists (misconfigured apply), we log loudly and continue
# so you can still SSH in and debug.
# -----------------------------------------------------------------------------

geopoai_find_data_disk() {
  local root_part root_disk
  root_part="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
  if [[ -z "${root_part}" ]]; then
    echo "[geopoai:mount] ERROR: could not resolve root filesystem device" >&2
    return 1
  fi

  # e.g. /dev/nvme0n1p1 -> nvme0n1 -> /dev/nvme0n1
  root_disk="/dev/$(lsblk -ndo PKNAME "${root_part}" 2>/dev/null || true)"
  if [[ ! -b "${root_disk}" ]]; then
    echo "[geopoai:mount] ERROR: could not resolve root disk from ${root_part}" >&2
    return 1
  fi

  echo "[geopoai:mount] root_part=${root_part} root_disk=${root_disk}" >&2

  local cand
  for cand in /dev/nvme*n1 /dev/vd[b-z] /dev/sd[b-z]; do
    [[ -b "${cand}" ]] || continue
    if [[ "${cand}" == "${root_disk}" ]]; then
      continue
    fi
    echo "${cand}"
    return 0
  done

  echo "[geopoai:mount] WARNING: no secondary data disk found (volume not attached?)" >&2
  return 1
}

geopoai_apt_install_mount_tools() {
  apt-get update -y
  apt-get install -y --no-install-recommends \
    e2fsprogs \
    util-linux \
    findutils \
    grep \
    gawk \
    coreutils \
    mount
}

geopoai_mount_device_at() {
  local dev="$1"
  local mp="$2"
  if findmnt -n -o TARGET,SOURCE "${mp}" 2>/dev/null | grep -qF "${dev}"; then
    echo "[geopoai:mount] ${mp} already mounted from ${dev}" >&2
    return 0
  fi
  mount -t ext4 "${dev}" "${mp}"
}

geopoai_mount_models_volume() {
  geopoai_apt_install_mount_tools

  local dev mp="/mnt/models"
  if ! dev="$(geopoai_find_data_disk)"; then
    mkdir -p "${mp}"
    echo "[geopoai:mount] continuing without dedicated volume mount" >&2
    return 0
  fi

  echo "[geopoai:mount] using data device: ${dev}" >&2
  mkdir -p "${mp}"

  if blkid "${dev}" | grep -qi ext4; then
    echo "[geopoai:mount] ext4 already present on ${dev}" >&2
    geopoai_mount_device_at "${dev}" "${mp}"
  else
    echo "[geopoai:mount] creating ext4 on ${dev} (first boot only)" >&2
    mkfs.ext4 -F -L geopoai-models "${dev}"
    geopoai_mount_device_at "${dev}" "${mp}"
  fi

  if ! grep -q '/mnt/models' /etc/fstab; then
    echo "LABEL=geopoai-models ${mp} ext4 defaults,nofail 0 2" >>/etc/fstab
  fi

  mkdir -p \
    "${mp}/checkpoints/ltx" \
    "${mp}/checkpoints/wan" \
    "${mp}/checkpoints/flux" \
    "${mp}/diffusion_models" \
    "${mp}/vae" \
    "${mp}/text_encoders" \
    "${mp}/latent_upscale_models" \
    "${mp}/diffusers" \
    "${mp}/loras" \
    "${mp}/controlnet" \
    "${mp}/input" \
    "${mp}/output" \
    "${mp}/user" \
    "${mp}/workflows" \
    "${mp}/training_sets"

  if id -u "${GEOPOAI_USER:-ubuntu}" &>/dev/null 2>&1; then
    chown -R "${GEOPOAI_USER}:${GEOPOAI_USER}" "${mp}" || true
  fi
  echo "[geopoai:mount] ${mp} ready" >&2
}

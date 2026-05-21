# -----------------------------------------------------------------------------
# geopoai_install_ssh_authorized_key — populate authorized_keys for GEOPOAI_USER
# GEOPOAI_SSH_PUBLIC_KEY_LINE is set by Terraform locals or repair_comfyui_setup.sh.
# -----------------------------------------------------------------------------

geopoai_install_ssh_authorized_key() {
  local key_line="${GEOPOAI_SSH_PUBLIC_KEY_LINE:-}"
  if [[ -z "${key_line}" ]]; then
    echo "[geopoai:ssh] ERROR: GEOPOAI_SSH_PUBLIC_KEY_LINE not set" >&2
    return 1
  fi
  local ssh_dir="${GEOPOAI_HOME}/.ssh"
  local auth_keys="${ssh_dir}/authorized_keys"
  mkdir -p "${ssh_dir}"
  touch "${auth_keys}"
  if ! grep -qxF "${key_line}" "${auth_keys}" 2>/dev/null; then
    echo "${key_line}" >> "${auth_keys}"
  fi
  if [[ "${GEOPOAI_USER}" == root ]]; then
    chmod 700 "${ssh_dir}"
    chmod 600 "${auth_keys}"
  else
    chown -R "${GEOPOAI_USER}:${GEOPOAI_USER}" "${ssh_dir}"
    chmod 700 "${ssh_dir}"
    chmod 600 "${auth_keys}"
  fi
  # Root-login images: also allow ubuntu@ if we just created that user
  if [[ "${GEOPOAI_USER}" == ubuntu ]] && [[ -d /root/.ssh ]] && [[ -f /root/.ssh/authorized_keys ]]; then
    grep -qxF "${key_line}" /root/.ssh/authorized_keys 2>/dev/null || \
      echo "${key_line}" >> /root/.ssh/authorized_keys
  fi
  echo "[geopoai:ssh] authorized_keys ready for ${GEOPOAI_USER} (${auth_keys})" >&2
}

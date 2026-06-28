# shellcheck shell=bash
# Shared helpers for infra/*.sh (sourced, not executed directly).

geopoai_infra_dir() {
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
}

geopoai_repo_root() {
  local infra
  infra="$(geopoai_infra_dir)"
  cd "${infra}/.." && pwd
}

geopoai_load_dotenv() {
  local root envf
  root="$(geopoai_repo_root)"
  envf="${root}/.env"
  if [[ -f "${envf}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${envf}"
    set +a
  fi
}

geopoai_tf_refresh_args() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return 0
  fi
  if [[ -n "${GEOPOAI_TF_REFRESH_ARGS:-}" ]]; then
    local -a _args
    read -r -a _args <<< "${GEOPOAI_TF_REFRESH_ARGS}"
    printf '%s\n' "${_args[@]}"
    return 0
  fi

  local infra run_id workload
  infra="$(geopoai_infra_dir)"
  cd "${infra}"

  if command -v terraform >/dev/null 2>&1; then
    run_id="$(terraform output -raw run_id 2>/dev/null || true)"
    workload="$(terraform output -raw workload 2>/dev/null || true)"
  fi

  if [[ -n "${run_id}" && "${run_id}" != "null" && -n "${workload}" && "${workload}" != "null" ]]; then
    local varfile="workloads/${workload}.tfvars"
    if [[ -f "${infra}/${varfile}" ]]; then
      printf '%s\n' "-var=run_id=${run_id}" "-var-file=${varfile}"
      return 0
    fi
  fi

  return 1
}

geopoai_ssh_public_key_line() {
  local infra pub
  infra="$(geopoai_infra_dir)"
  cd "${infra}"
  pub="$(terraform console -json 2>/dev/null <<< 'var.ssh_public_key_path' | tr -d '"' || true)"
  if [[ -n "${pub}" ]]; then
    pub="${pub/#\~/${HOME}}"
    if [[ -f "${pub}" ]]; then
      chomp <"${pub}"
      return 0
    fi
  fi
  if [[ -f "${HOME}/.ssh/id_ed25519.pub" ]]; then
    chomp <"${HOME}/.ssh/id_ed25519.pub"
    return 0
  fi
  return 1
}

chomp() {
  local s
  s="$(cat)"
  printf '%s' "${s%$'\n'}"
}

geopoai_resolve_ssh_private_key() {
  local infra pub priv
  if [[ -n "${GEOPOAI_SSH_IDENTITY:-}" && -f "${GEOPOAI_SSH_IDENTITY}" ]]; then
    echo "${GEOPOAI_SSH_IDENTITY}"
    return 0
  fi
  infra="$(geopoai_infra_dir)"
  cd "${infra}"
  pub="$(terraform console -json 2>/dev/null <<< 'var.ssh_public_key_path' | tr -d '"' || true)"
  if [[ -n "${pub}" ]]; then
    pub="${pub/#\~/${HOME}}"
    priv="${pub%.pub}"
    if [[ -f "${priv}" ]]; then
      echo "${priv}"
      return 0
    fi
  fi
  if [[ -f "${HOME}/.ssh/id_ed25519" ]]; then
    echo "${HOME}/.ssh/id_ed25519"
    return 0
  fi
  return 1
}

geopoai_wait_for_instance_ip() {
  local infra args=()
  infra="$(geopoai_infra_dir)"
  mapfile -t args < <(geopoai_tf_refresh_args 2>/dev/null || true)
  "${infra}/wait_for_instance_ip.sh" "${args[@]}"
}

# Push this checkout to the VM (repair path — avoids HTTPS git auth on the server).
geopoai_rsync_repo_to_vm() {
  local ip="$1"
  local identity="$2"
  local remote_user="${3:-root}"
  local repo_root="${4:-$(geopoai_repo_root)}"
  local remote_path="${5:-/home/ubuntu/GeoPoAI}"

  local ssh_opts=(
    -i "${identity}"
    -o IdentitiesOnly=yes
    -o StrictHostKeyChecking=accept-new
  )

  echo "[geopoai] rsync ${repo_root} -> ${remote_user}@${ip}:${remote_path}" >&2
  ssh "${ssh_opts[@]}" "${remote_user}@${ip}" "mkdir -p '${remote_path}'"

  local rsync_opts=(-az --delete)
  if [[ "${GEOPOAI_RSYNC_PROGRESS:-}" != "0" ]]; then
    rsync_opts+=(--info=progress2)
  fi

  # shellcheck disable=SC2029
  rsync "${rsync_opts[@]}" \
    -e "ssh -i '${identity}' -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
    --exclude '.env' \
    --exclude '.git/' \
    --exclude '.terraform/' \
    --exclude 'infra/.terraform/' \
    --exclude 'infra/terraform.tfstate' \
    --exclude 'infra/terraform.tfstate.*' \
    --exclude 'output/' \
    --exclude 'data/' \
    --exclude 'tmp/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.cursor/' \
    --exclude 'media/' \
    "${repo_root}/" "${remote_user}@${ip}:${remote_path}/"

  ssh "${ssh_opts[@]}" "${remote_user}@${ip}" "
    if id -u ubuntu &>/dev/null; then
      chown -R ubuntu:ubuntu '${remote_path}'
    fi
  "
}

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

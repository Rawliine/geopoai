#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# verda_ssh.sh — SSH into the Terraform-managed Verda instance (this directory)
# -----------------------------------------------------------------------------
# Uses the private key that pairs with variables.tf ssh_public_key_path (default
# ~/.ssh/id_ed25519). Override: GEOPOAI_SSH_IDENTITY=/path/to/private_key
#
# Usage (from repo root):
#   ./infra/verda_ssh.sh
#   ./infra/verda_ssh.sh -- tail -f /var/log/geopoai-bootstrap.log
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${INFRA_DIR}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "error: terraform not found in PATH" >&2
  exit 1
fi

geopoai_resolve_ssh_identity() {
  if [[ -n "${GEOPOAI_SSH_IDENTITY:-}" && -f "${GEOPOAI_SSH_IDENTITY}" ]]; then
    echo "${GEOPOAI_SSH_IDENTITY}"
    return 0
  fi

  local pub priv
  pub="$(terraform console -json 2>/dev/null <<< 'var.ssh_public_key_path' | tr -d '"' || true)"
  if [[ -n "${pub}" ]]; then
    pub="${pub/#\~/${HOME}}"
    priv="${pub%.pub}"
    if [[ -f "${priv}" ]]; then
      echo "${priv}"
      return 0
    fi
  fi

  for cand in "${HOME}/.ssh/id_ed25519" "${HOME}/.ssh/id_rsa"; do
    if [[ -f "${cand}" ]]; then
      echo "${cand}"
      return 0
    fi
  done
  return 1
}

SSH_IDENTITY="$(geopoai_resolve_ssh_identity)" || {
  echo "error: no SSH private key found (Terraform uses ssh_public_key_path, default ~/.ssh/id_ed25519.pub)." >&2
  echo "  Set GEOPOAI_SSH_IDENTITY to your private key path." >&2
  exit 1
}

SSH_OPTS=(
  -i "${SSH_IDENTITY}"
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=4
)

IP="$(terraform output -raw instance_ip 2>/dev/null || true)"
if [[ -z "${IP}" || "${IP}" == "null" ]]; then
  if [[ -x "${INFRA_DIR}/wait_for_instance_ip.sh" ]]; then
    echo "[geopoai] instance_ip not ready — waiting up to ${MAX_WAIT_SEC:-300}s..." >&2
    IP="$("${INFRA_DIR}/wait_for_instance_ip.sh")" || IP=""
  fi
fi
if [[ -z "${IP}" || "${IP}" == "null" ]]; then
  echo "error: instance_ip not set yet (Verda assigns IP after boot)." >&2
  echo "  Use: ./apply_comfyui_setup.sh <run_id> --watch" >&2
  echo "  Or:  ./wait_for_instance_ip.sh -var=run_id=... -var-file=workloads/comfyui.tfvars" >&2
  echo "  instance_id: $(terraform output -raw instance_id 2>/dev/null || echo '?')" >&2
  exit 1
fi

REMOTE_CMD=()
if [[ "${1:-}" == "--" ]]; then
  shift
  REMOTE_CMD=("$@")
elif [[ $# -gt 0 ]]; then
  REMOTE_CMD=("$@")
fi

echo "[geopoai] ssh -i ${SSH_IDENTITY} ubuntu@${IP}" >&2

if [[ ${#REMOTE_CMD[@]} -gt 0 ]]; then
  exec ssh "${SSH_OPTS[@]}" ubuntu@"${IP}" "${REMOTE_CMD[@]}"
else
  exec ssh "${SSH_OPTS[@]}" ubuntu@"${IP}"
fi

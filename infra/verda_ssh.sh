#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# verda_ssh.sh — SSH into the Terraform-managed Verda instance (this directory)
# -----------------------------------------------------------------------------
# Lives next to Terraform config so it does not occupy scripts/ (reserved for
# video / pipeline scripts at repo root).
#
# Prereqs:
#   - terraform apply has been run from this directory so outputs exist.
#   - Your SSH private key matches infra/variables.tf ssh_public_key_path.
#
# Usage (from repo root):
#   ./infra/verda_ssh.sh
#   ./infra/verda_ssh.sh tmux a -t comfyui
#
# Usage (from infra/):
#   ./verda_ssh.sh
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${INFRA_DIR}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "error: terraform not found in PATH" >&2
  exit 1
fi

IP="$(terraform output -raw instance_ip)"

REMOTE_CMD=()
if [[ "${1:-}" == "--" ]]; then
  shift
  REMOTE_CMD=("$@")
elif [[ $# -gt 0 ]]; then
  REMOTE_CMD=("$@")
fi

if [[ ${#REMOTE_CMD[@]} -gt 0 ]]; then
  exec ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=4 ubuntu@"${IP}" "${REMOTE_CMD[@]}"
else
  exec ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=4 ubuntu@"${IP}"
fi

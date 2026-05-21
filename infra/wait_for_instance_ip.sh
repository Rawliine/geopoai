#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# wait_for_instance_ip.sh — poll terraform refresh until instance_ip is assigned.
# Verda often returns ip=null for a few seconds after create; raw apply then errors
# on ssh_command output. Use after apply (or when verda_ssh.sh says IP missing).
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${INFRA_DIR}"

MAX_WAIT_SEC="${MAX_WAIT_SEC:-300}"
POLL_SEC="${POLL_SEC:-10}"

# Optional: pass the same -var / -var-file as apply. With existing state, plain refresh often works.
TF_ARGS=("$@")

if ! command -v terraform >/dev/null 2>&1; then
  echo "error: terraform not found in PATH" >&2
  exit 1
fi

echo "[geopoai] waiting for instance_ip (max ${MAX_WAIT_SEC}s, poll every ${POLL_SEC}s)..." >&2
deadline=$((SECONDS + MAX_WAIT_SEC))

while (( SECONDS < deadline )); do
  terraform refresh "${TF_ARGS[@]}" >/dev/null 2>&1 || true
  IP="$(terraform output -raw instance_ip 2>/dev/null || true)"
  if [[ -n "${IP}" && "${IP}" != "null" ]]; then
    echo "${IP}"
    exit 0
  fi
  ID="$(terraform output -raw instance_id 2>/dev/null || true)"
  echo "[geopoai] instance_id=${ID:-none} ip not ready yet (${SECONDS}s)..." >&2
  sleep "${POLL_SEC}"
done

echo "error: timed out waiting for instance_ip" >&2
exit 1

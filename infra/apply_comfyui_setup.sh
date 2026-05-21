#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# apply_comfyui_setup.sh — apply setup infra, tolerate delayed IP, optional log tail
#
# Bootstrap runs ON THE VERDA VM (startup script), not in this terminal.
# After apply, tails /var/log/geopoai-bootstrap.log over SSH by default.
#
# Usage:
#   cd infra
#   ./apply_comfyui_setup.sh setup-001              # apply → wait IP → tail bootstrap log
#   ./apply_comfyui_setup.sh setup-001 --no-watch   # apply → wait IP only
#   ./apply_comfyui_setup.sh setup-001 --apply-only # terraform apply only
#   ./repair_comfyui_setup.sh setup-001 --watch     # re-run bootstrap on existing VM
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${INFRA_DIR}/.." && pwd)"
cd "${INFRA_DIR}"
# shellcheck source=lib/geopoai_common.sh
source "${INFRA_DIR}/lib/geopoai_common.sh"

RUN_ID="${1:-}"
shift || true

WATCH=true
APPLY_ONLY=false
for arg in "$@"; do
  case "${arg}" in
    --watch) WATCH=true ;;
    --no-watch) WATCH=false ;;
    --apply-only) APPLY_ONLY=true; WATCH=false ;;
    *) echo "unknown arg: ${arg}" >&2; exit 1 ;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 <run_id> [--watch] [--apply-only]" >&2
  echo "  example: $0 setup-001 --watch" >&2
  exit 1
fi

geopoai_load_dotenv

TF_ARGS=(
  -var="run_id=${RUN_ID}"
  -var-file="workloads/comfyui.tfvars"
)

chmod +x \
  "${INFRA_DIR}/wait_for_instance_ip.sh" \
  "${INFRA_DIR}/verda_ssh.sh" \
  "${INFRA_DIR}/repair_comfyui_setup.sh" \
  "${INFRA_DIR}/scripts/resume_bootstrap_on_vm.sh" \
  2>/dev/null || true

echo "=============================================="
echo " GeoPoAI ComfyUI setup apply (run_id=${RUN_ID})"
echo " Bootstrap log on VM: /var/log/geopoai-bootstrap.log"
echo "=============================================="

APPLY_EXIT=0
terraform apply "${TF_ARGS[@]}" || APPLY_EXIT=$?

if [[ "${APPLY_EXIT}" -ne 0 ]]; then
  echo "[geopoai] terraform apply exited ${APPLY_EXIT} (often harmless if instance was created but IP was null)." >&2
fi

if [[ "${APPLY_ONLY}" == true ]]; then
  exit "${APPLY_EXIT}"
fi

echo "[geopoai] refreshing state until instance_ip is assigned..." >&2
IP="$("${INFRA_DIR}/wait_for_instance_ip.sh" "${TF_ARGS[@]}")"
echo "[geopoai] instance_ip=${IP}" >&2
terraform output instance_id ssh_command 2>/dev/null || true

export GEOPOAI_TF_REFRESH_ARGS="-var=run_id=${RUN_ID} -var-file=workloads/comfyui.tfvars"
# After apply, repair a VM that still has an old failed bootstrap (no replace needed):
#   ./repair_comfyui_setup.sh "${RUN_ID}" --watch

if [[ "${WATCH}" == true ]]; then
  echo "[geopoai] streaming bootstrap log (Ctrl-C to detach; VM keeps running)..." >&2
  exec "${INFRA_DIR}/verda_ssh.sh" -- tail -f /var/log/geopoai-bootstrap.log
fi

echo ""
echo "Next: ./verda_ssh.sh -- tail -f /var/log/geopoai-bootstrap.log"
echo "      ./verda_ssh.sh -- test -f /mnt/models/.geopoai_download_complete && echo done"

exit 0

#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# destroy_comfyui_instance.sh — tear down the GPU VM only (keeps /mnt/models volume)
#
# NEVER run bare `terraform destroy` — it will try to delete verda_volume.models
# (blocked by prevent_destroy, but still dangerous if that guard is removed).
#
# Usage:
#   ./destroy_comfyui_instance.sh setup-001
#   ./destroy_comfyui_instance.sh broll-ep017 --production
# -----------------------------------------------------------------------------
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${INFRA_DIR}"

RUN_ID="${1:-}"
shift || true

if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 <run_id> [--production]" >&2
  echo "  example: $0 setup-001" >&2
  echo "  example: $0 broll-ep017 --production   # same var-files as production apply" >&2
  exit 1
fi

TF_ARGS=(
  -target=verda_instance.this
  -var="run_id=${RUN_ID}"
  -var-file=workloads/comfyui.tfvars
)

for arg in "$@"; do
  case "${arg}" in
    --production)
      TF_ARGS+=(-var-file=workloads/comfyui_production.tfvars)
      ;;
    *)
      echo "unknown arg: ${arg}" >&2
      exit 1
      ;;
  esac
done

echo "=============================================="
echo " GeoPoAI — destroy INSTANCE only (run_id=${RUN_ID})"
echo " Models volume geopoai-models-persistent is KEPT."
echo "=============================================="

terraform destroy "${TF_ARGS[@]}"

echo ""
echo "[geopoai] instance destroyed. Volume still in Verda + Terraform state."
echo "  terraform output models_volume_id   # after a future apply"
echo "  To delete the volume intentionally: remove prevent_destroy in compute.tf,"
echo "  then: terraform destroy -target=verda_volume.models (same -var/-var-file)."

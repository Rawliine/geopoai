# -----------------------------------------------------------------------------
# Production overrides — use AFTER setup (models on /mnt/models, marker present).
# Apply with BOTH var-files (same run_id pattern as setup):
#   terraform apply -var="run_id=broll-ep017" \
#     -var-file="workloads/comfyui.tfvars" \
#     -var-file="workloads/comfyui_production.tfvars"
# -----------------------------------------------------------------------------
# Confirm H100 string in Verda dashboard for FIN-03.
gpu_type = "1H100.80S.30V"

# Batch / overnight generation: spot (~65% cheaper than on-demand on H100).
use_spot = true

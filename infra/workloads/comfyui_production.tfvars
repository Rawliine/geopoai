# -----------------------------------------------------------------------------
# Production overrides — use AFTER setup (models on /mnt/models, marker present).
# Use the same location as comfyui.tfvars (e.g. FIN-01).
#
# Apply (new run_id per session):
#   terraform apply -var="run_id=broll-ep017" \
#     -var-file="workloads/comfyui.tfvars" \
#     -var-file="workloads/comfyui_production.tfvars"
#
# Destroy VM only (volume kept):
#   ./destroy_comfyui_instance.sh broll-ep017 --production
# -----------------------------------------------------------------------------
# Confirm H100 string + image in Verda dashboard (same location as comfyui.tfvars).
gpu_type = "1H100.80S.30V"
verda_image = "ubuntu-24.04-cuda-13.0-open-docker"

# Batch / overnight generation: spot (~65% cheaper than on-demand on H100).
use_spot = true

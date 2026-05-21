# -----------------------------------------------------------------------------
# Inference when H100/L40S unavailable — RTX A6000 48GB, spot.
# Apply with comfyui.tfvars (production.tfvars overrides gpu back to H100):
#   terraform apply -var="run_id=broll-test-001" \
#     -var-file=workloads/comfyui.tfvars \
#     -var-file=workloads/comfyui_a6000_spot.tfvars
# Destroy: ./destroy_comfyui_instance.sh broll-test-001 --a6000
# -----------------------------------------------------------------------------
gpu_type    = "1A6000.10V"
use_spot    = true
verda_image = "ubuntu-22.04-cuda-12.4-docker"

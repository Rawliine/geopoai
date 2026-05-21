# -----------------------------------------------------------------------------
# Workload profile: ComfyUI (LTX / Wan / FLUX + LoRAs on /mnt/models)
# -----------------------------------------------------------------------------
# **Setup phase (current):** cheaper GPU + on-demand — model download + bootstrap only.
# **Production batch:** use the second var-file:
#   terraform apply -var="run_id=..." \
#     -var-file="workloads/comfyui.tfvars" \
#     -var-file="workloads/comfyui_production.tfvars"
#
# Apply setup (first time):
#   cd infra && set -a && source ../.env && set +a
#   terraform apply -var="run_id=setup-001" -var-file="workloads/comfyui.tfvars"
# -----------------------------------------------------------------------------

workload = "comfyui"

# Setup: L40S on-demand (~$1.36/h FIN region — confirm in Verda dashboard for FIN-03).
# Downloads are network-bound; you do not need H100 until inference.
gpu_type = "1L40S.20V"

# Setup: on-demand so long bootstrap/download is not interrupted by spot eviction.
use_spot = false

# GeoPoAI repo (HTTPS public clone works without deploy keys).
geopoai_git_repo = "https://github.com/Rawliine/geopoai.git"

# Hugging Face token: set TF_VAR_huggingface_token in ../.env (not in this file).
# Accept licenses on huggingface.co for Lightricks/LTX-2.3 before first boot.

# ComfyUI listen port (remember SSH port-forwarding if the network is untrusted).
# comfyui_listen_port = 8188

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

# Must match where GPUs are free in the Verda dashboard (volume + instance same region).
location = "FIN-01"

# Setup instance (on-demand). Downloads are network-bound — any free GPU in `location` is fine.
# Flow: setup VM → fills /mnt/models → terraform destroy → production GPU later.
# V100 is enough for bootstrap; LTX/Wan/FLUX inference usually needs H100/RTX PRO (production tfvars).
gpu_type = "1V100.6V"

# V100 supported_os (Verda API): ubuntu-22.04-cuda-12.4-docker, ubuntu-24.04-cuda-12.6-docker — NOT cuda-12.8/13.
verda_image = "ubuntu-22.04-cuda-12.4-docker"

# Setup: on-demand so long bootstrap/download is not interrupted by spot eviction.
use_spot = false

# GeoPoAI repo (HTTPS public clone works without deploy keys).
geopoai_git_repo = "https://github.com/Rawliine/geopoai.git"

# Hugging Face token: set TF_VAR_huggingface_token in ../.env (not in this file).
# Accept licenses on huggingface.co for Lightricks/LTX-2.3 before first boot.

# ComfyUI listen port (remember SSH port-forwarding if the network is untrusted).
# comfyui_listen_port = 8188

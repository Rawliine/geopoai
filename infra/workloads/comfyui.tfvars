# -----------------------------------------------------------------------------
# Workload profile: ComfyUI (LTX / Wan / FLUX + LoRAs on /mnt/models)
# -----------------------------------------------------------------------------
# **Setup phase (current):** cheaper GPU + on-demand — model download + bootstrap only.
# **Production batch:** use the second var-file:
#   terraform apply -var="run_id=..." \
#     -var-file="workloads/comfyui.tfvars" \
#     -var-file="workloads/comfyui_production.tfvars"
#
# Apply setup (first time — waits for IP, tails bootstrap log):
#   cd infra && ./apply_comfyui_setup.sh setup-001
# Repair a VM after a failed bootstrap (no instance replace):
#   ./repair_comfyui_setup.sh setup-001 --watch
# -----------------------------------------------------------------------------

workload = "comfyui"

# Must match where GPUs are free in the Verda dashboard (volume + instance same region).
location = "FIN-01"

# Setup instance (on-demand). Downloads are network-bound — any free GPU in `location` is fine.
#
# GPU phases (all manual — no auto-switch):
#   1) SETUP     — this file only (cheap GPU, on-demand) → download_models → marker on volume
#   2) ITERATION — optional: same or production GPU; tune broll workflows; ./destroy_comfyui_instance.sh when done
#   3) PRODUCTION — add comfyui_production.tfvars (H100 spot) for batch inference
# Between phases: ./destroy_comfyui_instance.sh <run_id>  (NOT terraform destroy)
# V100 is enough for bootstrap; LTX/Wan/FLUX inference usually needs H100 (production tfvars).
gpu_type = "1V100.6V"
verda_image = "ubuntu-22.04-cuda-12.4-docker"

# Setup: on-demand so long bootstrap/download is not interrupted by spot eviction.
use_spot = false

# GeoPoAI repo (HTTPS public clone works without deploy keys).
geopoai_git_repo = "https://github.com/Rawliine/geopoai.git"

# Hugging Face token: set TF_VAR_huggingface_token in ../.env (not in this file).
# Accept licenses on huggingface.co for Lightricks/LTX-2.3 before first boot.

# ComfyUI listen port (remember SSH port-forwarding if the network is untrusted).
# comfyui_listen_port = 8188

# -----------------------------------------------------------------------------
# Workload profile: ComfyUI (LTX / Wan / FLUX + LoRAs on /mnt/models)
# -----------------------------------------------------------------------------
# Apply example (run_id keeps hostnames + OS volumes unique per job):
#   cd infra
#   export VERDA_CLIENT_ID=... VERDA_CLIENT_SECRET=...
#   terraform apply -var="run_id=broll-ep017" -var-file="workloads/comfyui.tfvars"
#
# Spot vs on-demand (from verda_workflow doc):
#   - Batch generation  → use_spot = true
#   - Interactive debug → use_spot = false
# -----------------------------------------------------------------------------

workload = "comfyui"

# Verda instance type string — confirm in dashboard catalog for FIN-03.
gpu_type = "1H100.80S.30V"

# Batch / overnight jobs: true. Short interactive debugging sessions: false.
use_spot = true

# Required for first automated launch: GeoPoAI repo (SSH deploy key on instance, or HTTPS).
# Example: geopoai_git_repo = "git@github.com:YOUR_USER/GeoPoAI.git"
geopoai_git_repo = ""

# Hugging Face read token — pass via -var or TF_VAR_huggingface_token (sensitive).
# Accept licenses on huggingface.co for Lightricks/LTX-2.3 before first boot.
# huggingface_token = "hf_..."

# First-time setup: use on-demand (use_spot = false) so bootstrap is not interrupted.
# use_spot = false

# ComfyUI listen port (remember SSH port-forwarding if the network is untrusted).
# comfyui_listen_port = 8188

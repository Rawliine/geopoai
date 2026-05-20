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

# Optional: clone your fork for on-VM iteration (HTTPS or SSH URL).
# Leave empty to skip; you can always `git clone` manually after SSH.
geopoai_git_repo = ""

# ComfyUI listen port (remember SSH port-forwarding if the network is untrusted).
# comfyui_listen_port = 8188

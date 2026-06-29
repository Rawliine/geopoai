# -----------------------------------------------------------------------------
# Workload profile: Fish Audio S2-Pro TTS API server (voice-over generation)
# -----------------------------------------------------------------------------
# Separate from ComfyUI — its own bootstrap (startup_scripts/s2pro_bootstrap.sh).
# Shares only the persistent /mnt/models volume (weights in checkpoints/s2-pro)
# and the common user/mount/ssh/deadman libs. The ComfyUI/LTX bootstrap is never
# modified or run by this workload.
#
# Prereqs:
#   - Accept the Fish Audio Research License (NON-COMMERCIAL) at
#     huggingface.co/fishaudio/s2-pro
#   - TF_VAR_huggingface_token set in ../.env
#
# Bring up:
#   cd infra && terraform apply -var="run_id=s2pro-001" -var-file="workloads/s2pro.tfvars"
#   ./verda_ssh.sh -- tail -f /var/log/geopoai-bootstrap.log   # watch download + serve
#   ./verda_ssh.sh -- tmux a -t s2pro                          # the api_server session
# Tear down (keeps the models volume):
#   ./destroy_comfyui_instance.sh s2pro-001
# -----------------------------------------------------------------------------

workload = "s2pro"

# Same region as the persistent models volume (instance + volume must match).
location = "FIN-01"

# S2-Pro is ~4.4B params (Slow-AR 4B + Fast-AR 400M). A6000 (48 GB) is comfortable
# for fp16 inference. On-demand for serving stability (spot eviction kills the
# server mid-batch). Swap to a smaller/cheaper GPU once you know the footprint.
gpu_type    = "1A6000.10V"
use_spot    = false
verda_image = "ubuntu-22.04-cuda-12.4-docker"

# GeoPoAI checkout not needed on the box — the bootstrap clones fish-speech itself.
geopoai_git_repo = ""

# api_server listen port (SSH-tunnel it; do not expose publicly).
# s2pro_listen_port = 8888

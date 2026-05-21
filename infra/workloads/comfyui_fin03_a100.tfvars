# -----------------------------------------------------------------------------
# FIN-03 — 1× A100 22V, on-demand (stable bootstrap + inference).
# Volume and instance MUST both be in FIN-03 (cannot attach FIN-01 block volume).
#
# First time in FIN-03 (new empty volume → download ~200 GiB):
#   terraform state rm verda_volume.models   # only drops from state; FIN-01 disk unchanged in Verda
#   terraform apply -var="run_id=broll-fin03-001" \
#     -var-file=workloads/comfyui.tfvars \
#     -var-file=workloads/comfyui_fin03_a100.tfvars
#
# Destroy VM only:
#   ./destroy_comfyui_instance.sh broll-fin03-001 --fin03
#
# If apply errors "Startup scripts cannot be updated" after changing run_id:
#   terraform apply -replace=verda_startup_script.this ... (same -var/-var-file)
# -----------------------------------------------------------------------------
location    = "FIN-03"
gpu_type    = "1A100.22V"
use_spot    = false
verda_image = "ubuntu-22.04-cuda-12.4-docker"

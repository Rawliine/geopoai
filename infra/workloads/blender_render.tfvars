# -----------------------------------------------------------------------------
# Workload profile: Blender Cycles / batch renders on Verda
# -----------------------------------------------------------------------------
# Workflow: apply → rsync .blend + assets → SSH → `blender --background …` →
# rsync outputs back → destroy. OS disk can go away; keep heavy outputs on
# /mnt/models/output if you want them on the persistent volume.
#
# Example:
#   terraform apply -var="run_id=presenter-cycles-ep017" -var-file="workloads/blender_render.tfvars"
# -----------------------------------------------------------------------------

workload = "blender_render"

# Pick a GPU/CPU mix appropriate to your scene. Many Cycles jobs scale with GPU;
# confirm the exact Verda type strings in the console catalog.
gpu_type = "1H100.80S.30V"

# Frame batches are embarrassingly parallel — spot is usually fine.
use_spot = true

geopoai_git_repo = ""

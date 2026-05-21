# -----------------------------------------------------------------------------
# Locals — derived names and the rendered Verda startup script payload.
# -----------------------------------------------------------------------------
# The startup script is assembled in this order:
#   1) Bash strict mode + logging
#   2) lib_mount.sh — defines geopoai_mount_models_volume()
#   3) geopoai_mount_models_volume — formats & mounts /mnt/models from the first non-root disk
#   4) Workload body:
#        - comfyui:        template comfyui_bootstrap.tftpl (ComfyUI install + tmux)
#        - lora_train:     lora_bootstrap.sh (packages + hints)
#        - blender_render: render_blender.sh (blender + output dirs)
# -----------------------------------------------------------------------------

locals {
  default_hostname_prefix = {
    comfyui        = "comfyui"
    lora_train     = "lora-train"
    blender_render = "blender"
  }[var.workload]

  hostname_prefix = var.hostname_prefix != "" ? var.hostname_prefix : local.default_hostname_prefix
  hostname        = "${local.hostname_prefix}-${var.run_id}"

  mount_library = file("${path.module}/startup_scripts/lib_mount.sh")

  workload_body = (
    var.workload == "comfyui" ? templatefile("${path.module}/startup_scripts/comfyui_bootstrap.tftpl", {
      geopoai_git_repo    = var.geopoai_git_repo
      comfyui_listen_port = var.comfyui_listen_port
      huggingface_token   = var.huggingface_token
    }) :
    var.workload == "lora_train" ? file("${path.module}/startup_scripts/lora_bootstrap.sh") :
    file("${path.module}/startup_scripts/render_blender.sh")
  )

  startup_script_verda_name = "${var.project_slug}-${var.workload}-${var.run_id}-bootstrap"

  startup_script = join("\n", [
    "#!/usr/bin/env bash",
    "# GeoPoAI Verda bootstrap — assembled by Terraform (locals.tf)",
    "set -euo pipefail",
    "export DEBIAN_FRONTEND=noninteractive",
    "exec > >(tee -a /var/log/geopoai-bootstrap.log) 2>&1",
    "echo \"[geopoai] bootstrap start $(date -Is) workload=${var.workload} host=$(hostname)\"",
    local.mount_library,
    "geopoai_mount_models_volume",
    local.workload_body,
    "echo \"[geopoai] bootstrap finished OK $(date -Is)\"",
  ])
}

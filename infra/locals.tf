# -----------------------------------------------------------------------------
# Locals — derived names and the rendered Verda startup script payload.
# -----------------------------------------------------------------------------
# The startup script is assembled in this order:
#   1) Bash strict mode + logging
#   2) lib_user.sh — defines geopoai_ensure_login_user()
#   3) geopoai_ensure_login_user
#   4) lib_mount.sh — geopoai_mount_models_volume()
#   5) lib_ssh_access.sh — geopoai_install_ssh_authorized_key()
#   6) ComfyUI env exports + lib_apt_comfyui.sh + comfyui_bootstrap.sh
#   7) Other workloads: lora_bootstrap.sh / render_blender.sh
# -----------------------------------------------------------------------------

locals {
  default_hostname_prefix = {
    comfyui        = "comfyui"
    lora_train     = "lora-train"
    blender_render = "blender"
  }[var.workload]

  hostname_prefix = var.hostname_prefix != "" ? var.hostname_prefix : local.default_hostname_prefix
  hostname        = "${local.hostname_prefix}-${var.run_id}"

  # verda_instance requires description (Verda API / provider ~> 1.0).
  instance_description = "GeoPoAI ${var.workload} — ${local.hostname}"

  user_library        = file("${path.module}/startup_scripts/lib_user.sh")
  mount_library       = file("${path.module}/startup_scripts/lib_mount.sh")
  apt_comfyui_library = file("${path.module}/startup_scripts/lib_apt_comfyui.sh")

  ssh_public_key_line = chomp(file(pathexpand(var.ssh_public_key_path)))

  ssh_access_library = file("${path.module}/startup_scripts/lib_ssh_access.sh")

  ssh_env_export = "export GEOPOAI_SSH_PUBLIC_KEY_LINE=${jsonencode(local.ssh_public_key_line)}"

  deadman_env_exports = join("\n", compact([
    "export GEOPOAI_MAX_SESSION_HOURS=${jsonencode(tostring(var.max_session_hours))}",
    var.verda_client_id != "" ? "export VERDA_CLIENT_ID=${jsonencode(var.verda_client_id)}" : "",
    var.verda_client_secret != "" ? "export VERDA_CLIENT_SECRET=${jsonencode(var.verda_client_secret)}" : "",
  ]))

  deadman_library = file("${path.module}/startup_scripts/lib_deadman.sh")

  comfyui_env_exports = var.workload == "comfyui" ? join("\n", compact([
    "export GEOPOAI_GIT_REPO=${jsonencode(var.geopoai_git_repo)}",
    "export COMFYUI_LISTEN_PORT=${jsonencode(tostring(var.comfyui_listen_port))}",
    var.huggingface_token != "" ? "export HF_TOKEN=${jsonencode(var.huggingface_token)}" : "",
    var.huggingface_token != "" ? "export HUGGING_FACE_HUB_TOKEN=\"$${HF_TOKEN}\"" : "",
  ])) : ""

  comfyui_body = join("\n", [
    local.apt_comfyui_library,
    file("${path.module}/startup_scripts/comfyui_bootstrap.sh"),
  ])

  workload_body = (
    var.workload == "comfyui" ? local.comfyui_body :
    var.workload == "lora_train" ? file("${path.module}/startup_scripts/lora_bootstrap.sh") :
    file("${path.module}/startup_scripts/render_blender.sh")
  )

  # Verda startup scripts are immutable — change this suffix to force a new script object.
  # Verda does not allow in-place startup script updates — keep name stable across run_id.
  startup_script_verda_name = "${var.project_slug}-${var.workload}-bootstrap-v6"

  startup_script = join("\n", [
    "#!/usr/bin/env bash",
    "# GeoPoAI Verda bootstrap — assembled by Terraform (locals.tf)",
    "set -euo pipefail",
    "export DEBIAN_FRONTEND=noninteractive",
    "exec > >(tee -a /var/log/geopoai-bootstrap.log) 2>&1",
    "echo \"[geopoai] bootstrap start $(date -Is) workload=${var.workload} host=$(hostname)\"",
    local.user_library,
    "geopoai_ensure_login_user",
    local.mount_library,
    "geopoai_mount_models_volume",
    local.ssh_env_export,
    local.deadman_env_exports,
    local.ssh_access_library,
    "geopoai_install_ssh_authorized_key",
    local.deadman_library,
    local.comfyui_env_exports,
    local.workload_body,
    "echo \"[geopoai] bootstrap finished OK $(date -Is)\"",
  ])
}

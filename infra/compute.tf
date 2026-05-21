# -----------------------------------------------------------------------------
# Verda resources — SSH key, persistent volume, startup script, instance.
# -----------------------------------------------------------------------------
# Mental model (from infra/verda_workflow*.md):
#   - Block volume  → long-lived model / LoRA / dataset storage at /mnt/models
#   - Instance + OS disk → ephemeral compute; destroy when idle
#   - Startup script → first-boot automation (mount + workload-specific setup)
#
# After changing startup scripts or Terraform versions:
#   terraform fmt && terraform init -upgrade && terraform validate
#
# Provider field names MUST match the published provider schema. If `terraform
# validate` fails after init, compare this file to:
#   https://registry.terraform.io/providers/verda-cloud/verda/latest/docs
# -----------------------------------------------------------------------------

resource "verda_ssh_key" "this" {
  name       = "${var.project_slug}-${var.ssh_key_name_suffix}"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "verda_volume" "models" {
  name     = "${var.project_slug}-${var.models_volume_name_suffix}"
  size     = var.models_volume_size_gb
  type     = var.models_volume_type
  location = var.location

  # Full `terraform destroy` must NOT delete ~200 GiB of weights. Use
  # ./destroy_comfyui_instance.sh (targets only verda_instance.this).
  lifecycle {
    prevent_destroy = true
  }
}

resource "verda_startup_script" "this" {
  name   = local.startup_script_verda_name
  script = local.startup_script

  lifecycle {
    create_before_destroy = true
  }
}

resource "verda_instance" "this" {
  instance_type       = var.gpu_type
  image               = var.verda_image
  hostname            = local.hostname
  description         = local.instance_description
  location            = var.location
  is_spot             = var.use_spot
  ssh_key_ids         = [verda_ssh_key.this.id]
  startup_script_id   = verda_startup_script.this.id
  existing_volumes    = [verda_volume.models.id]

  os_volume = {
    name                = "${local.hostname_prefix}-os-${var.run_id}"
    size                = var.os_volume_size_gb
    type                = var.os_volume_type
    on_spot_discontinue = var.os_volume_on_spot_discontinue
  }
}

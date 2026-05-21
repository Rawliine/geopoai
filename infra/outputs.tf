# -----------------------------------------------------------------------------
# Outputs — convenient values after `terraform apply`.
# -----------------------------------------------------------------------------

output "workload" {
  description = "Echo of the workload variable for sanity checks."
  value       = var.workload
}

output "hostname" {
  description = "Verda hostname assigned to the instance."
  value       = local.hostname
}

output "run_id" {
  description = "Run id passed to terraform apply (-var=run_id=...)."
  value       = var.run_id
}

output "instance_ip" {
  description = "Primary IP address returned by the Verda provider for SSH. May be null immediately after create — run terraform refresh with the same -var/-var-file, then re-output."
  value       = verda_instance.this.ip
}

output "ssh_command" {
  description = "Copy-paste SSH command (StrictHostKeyChecking not set here — use infra/verda_ssh.sh for accept-new)."
  value = (
    verda_instance.this.ip != null
    ? "ssh ubuntu@${verda_instance.this.ip}"
    : "ssh ubuntu@<pending>  # IP not ready yet: terraform refresh -var=run_id=... -var-file=workloads/comfyui.tfvars"
  )
}

output "instance_id" {
  description = "Verda instance id (useful when IP is still null right after apply)."
  value       = verda_instance.this.id
}

output "models_volume_id" {
  description = "Verda block volume id for /mnt/models (persists across instance destroy)."
  value       = verda_volume.models.id
}

output "reminder" {
  description = "Operational reminder printed after apply."
  value       = "Destroy VM only (keeps models volume): ./destroy_comfyui_instance.sh ${var.run_id}. Do NOT run bare terraform destroy."
}

output "models_volume_name" {
  description = "Verda dashboard name for the persistent block volume."
  value       = "${var.project_slug}-${var.models_volume_name_suffix}"
}

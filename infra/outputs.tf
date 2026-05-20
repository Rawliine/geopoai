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

output "instance_ip" {
  description = "Primary IP address returned by the Verda provider for SSH."
  value       = verda_instance.this.ip
}

output "ssh_command" {
  description = "Copy-paste SSH command (StrictHostKeyChecking not set here — use infra/verda_ssh.sh for accept-new)."
  value       = "ssh ubuntu@${verda_instance.this.ip}"
}

output "models_volume_id" {
  description = "Verda block volume id for /mnt/models (persists across instance destroy)."
  value       = verda_volume.models.id
}

output "reminder" {
  description = "Operational reminder printed after apply."
  value       = "Destroy the instance when idle: terraform destroy -var=\"run_id=${var.run_id}\" -var-file=workloads/<same>.tfvars. The models volume is kept unless you remove it from Terraform."
}

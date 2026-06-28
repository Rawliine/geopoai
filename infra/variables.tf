# -----------------------------------------------------------------------------
# Input variables — set via CLI (-var / -var-file) or TF_VAR_* for automation.
# -----------------------------------------------------------------------------
# Typical flow (see README.md):
#   cd infra
#   terraform apply -var="run_id=broll-ep017" -var-file="workloads/comfyui.tfvars"
# -----------------------------------------------------------------------------

variable "workload" {
  type        = string
  description = <<-EOT
    Which bootstrap + defaults this apply represents:
      - comfyui        — ComfyUI + persistent /mnt/models (LTX / Wan / FLUX workflows)
      - lora_train     — Lightweight GPU box: volume mounted, you install ai-toolkit / kohya manually
      - blender_render — CPU/GPU Blender batch helpers (apt installs blender; you rsync projects + run renders)
  EOT

  validation {
    condition     = contains(["comfyui", "lora_train", "blender_render"], var.workload)
    error_message = "workload must be one of: comfyui, lora_train, blender_render."
  }
}

variable "project_slug" {
  type        = string
  description = "Short prefix for Terraform-managed Verda object names (SSH key, volume, startup script)."
  default     = "geopoai"
}

variable "run_id" {
  type        = string
  description = "Unique token for this machine (episode id, timestamp, experiment name). Drives hostname + OS volume name uniqueness."

  validation {
    condition     = can(regex("^[a-zA-Z0-9-]+$", var.run_id))
    error_message = "run_id must contain only alphanumeric characters and dashes (Verda hostname rule)."
  }
}

variable "gpu_type" {
  type        = string
  description = "Verda instance type string, e.g. 1H100.80S.30V. Must exist in Verda's catalog for your account/region."
}

variable "use_spot" {
  type        = bool
  description = "true = spot pricing (cheaper, interruptible). false = on-demand (stable for interactive ComfyUI debugging)."
}

variable "location" {
  type        = string
  description = "Verda location / site code (e.g. FIN-03). Must match volume + instance + any org policy."
  default     = "FIN-03"
}

variable "hostname_prefix" {
  type        = string
  description = "Hostname prefix before run_id. Leave empty to use workload defaults (comfyui / lora-train / blender)."
  default     = ""
}

variable "verda_image" {
  type        = string
  description = "Verda image slug. Must be valid for instance_type (e.g. V100 → cuda-12.x; H100 → cuda-13.x). See dashboard or GET /images."
  default     = "ubuntu-24.04-cuda-13.0-open-docker"
}

variable "ssh_public_key_path" {
  type        = string
  description = "Local path to the SSH *public* key to register with Verda (~ expanded automatically). Override if you use a non-default key name."
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_key_name_suffix" {
  type        = string
  description = "Suffix for the Verda-side SSH key object name (full name is project_slug + this)."
  default     = "primary"
}

variable "models_volume_size_gb" {
  type        = number
  description = "Persistent block volume size for /mnt/models (model weights, LoRAs, datasets). Billed monthly even without a running instance. Default 280 GB fits LTX + Wan T2V/I2V + FLUX.2 + headroom."
  default     = 280
}

variable "models_volume_type" {
  type        = string
  description = "Verda volume type (per catalog), e.g. NVMe."
  default     = "NVMe"
}

variable "models_volume_name_suffix" {
  type        = string
  description = "Verda volume name becomes: {project_slug}-{this suffix}. Keep stable so the same disk is reused across destroys."
  default     = "models-persistent"
}

variable "os_volume_size_gb" {
  type        = number
  description = "Boot / OS disk size for the ephemeral instance."
  default     = 100
}

variable "os_volume_type" {
  type        = string
  description = "OS volume type (per Verda catalog)."
  default     = "NVMe"
}

variable "os_volume_on_spot_discontinue" {
  type        = string
  description = "What Verda should do with the OS volume when a spot instance is discontinued. delete_permanently matches the workflow doc."
  default     = "delete_permanently"
}

variable "geopoai_git_repo" {
  type        = string
  description = "Optional HTTPS or SSH URL to clone GeoPoAI (or your fork) into /home/ubuntu/GeoPoAI for on-VM iteration. Empty skips clone."
  default     = ""
}

variable "comfyui_listen_port" {
  type        = number
  description = "ComfyUI --listen port (exposed on the instance LAN; secure with SSH tunnel or Verda firewall rules as appropriate)."
  default     = 8188
}

variable "huggingface_token" {
  type        = string
  description = "Hugging Face read token for gated model downloads on first boot (export as HF_TOKEN in bootstrap). Accept FLUX/LTX licenses on huggingface.co first. Leave empty only if models are already on the volume."
  default     = ""
  sensitive   = true
}

variable "max_session_hours" {
  type        = number
  description = "Hard session budget cap (hours) for laptop watchdog + VM dead-man cron backstop."
  default     = 8
}

variable "verda_client_id" {
  type        = string
  description = "Verda API client id for VM dead-man cron (optional; falls back to VERDA_CLIENT_ID at apply time)."
  default     = ""
  sensitive   = true
}

variable "verda_client_secret" {
  type        = string
  description = "Verda API client secret for VM dead-man cron (optional; falls back to VERDA_CLIENT_SECRET at apply time)."
  default     = ""
  sensitive   = true
}

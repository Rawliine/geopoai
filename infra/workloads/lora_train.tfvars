# -----------------------------------------------------------------------------
# Workload profile: LoRA / fine-tuning box (long-running, checkpoint-heavy)
# -----------------------------------------------------------------------------
# The bootstrap script only mounts /mnt/models and installs base packages.
# You install ai-toolkit / kohya / etc. after SSH so you can pin versions.
#
# Example:
#   terraform apply -var="run_id=lora-channel-v3" -var-file="workloads/lora_train.tfvars"
# -----------------------------------------------------------------------------

workload = "lora_train"

# Same H100 class as ComfyUI batches — long jobs benefit from big VRAM.
gpu_type = "1H100.80S.30V"

# Training is a classic spot workload IF you checkpoint to /mnt/models often.
use_spot = true

geopoai_git_repo = ""

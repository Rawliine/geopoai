# GeoPoAI → Verda infrastructure (Terraform)

This directory turns the personal playbook in `verda_workflow(2).md` into **repeatable, versioned infrastructure**: one persistent **block volume** for models/LoRAs/datasets, and **ephemeral GPU instances** you bring up for batches and destroy when idle.

If you only read one section: **Credentials → First apply → SSH → Destroy**.

**Per-file map of this directory** (what each file does alone vs as a system): **`INFRA_FILE_REFERENCE.md`**.

---

## What you get

| Piece | Purpose |
|-------|---------|
| `verda_ssh_key` | Registers your laptop’s **public** SSH key with Verda once. |
| `verda_volume` | **Persistent** NVMe volume mounted at **`/mnt/models`** on the instance (survives `terraform destroy` of the VM). |
| `verda_startup_script` | First-boot shell script: mount volume + workload-specific setup. |
| `verda_instance` | The actual GPU VM (spot or on-demand). OS disk is separate from `/mnt/models`. |

Three **workloads** share the same Terraform code; you pick one via `-var-file`:

| `workload` value | `workloads/*.tfvars` | What the startup script does |
|------------------|----------------------|--------------------------------|
| `comfyui` | `comfyui.tfvars` | Installs ComfyUI under `/home/ubuntu/ComfyUI`, symlinks heavy model dirs to `/mnt/models/*`, starts **tmux** session `comfyui` listening on `0.0.0.0:8188`. |
| `lora_train` | `lora_train.tfvars` | Mounts `/mnt/models`, installs dev basics (`git`, `python3`, `tmux`, `nvtop`, …). **You** install ai-toolkit / kohya after SSH so you can pin revisions. |
| `blender_render` | `blender_render.tfvars` | Mounts `/mnt/models`, `apt install`s **Blender**, prepares `~/outputs` + `~/renders` for batch jobs. |

---

## Prerequisites

1. **Verda account** with billing + **budget alerts** configured (see workflow doc).
2. **API credentials**: Dashboard → *Keys* → *Cloud API Credentials* → create → save `client_id` + `client_secret` (secret shown once).
3. **Terraform** ≥ 1.5 (`terraform version`) or OpenTofu (`tofu`).
4. **SSH key pair** on your laptop; by default Terraform reads **`~/.ssh/id_rsa.pub`** (override with `ssh_public_key_path`).

---

## Credentials (important)

Terraform’s Verda provider reads **environment variables**, not your repo `.env`, unless you explicitly export from it:

```bash
export VERDA_CLIENT_ID="…"
export VERDA_CLIENT_SECRET="…"
```

Optional ergonomics:

```bash
set -a
source ../.env   # only if you keep VERDA_* keys there (never commit secrets)
set +a
```

Suggested `.env` names (must match what the provider expects):

- `VERDA_CLIENT_ID`
- `VERDA_CLIENT_SECRET`

---

## First-time setup

```bash
cd infra
terraform init          # downloads the verda-cloud/verda provider
terraform fmt -recursive  # optional but recommended
terraform validate        # requires successful init
```

> **Schema drift:** if `terraform validate` errors on argument names (`existing_volumes`, `os_volume`, …), compare `compute.tf` to the current provider docs:  
> https://registry.terraform.io/providers/verda-cloud/verda/latest/docs

---

## Day-to-day commands

Always pass a fresh **`run_id`** per job so hostnames and OS volume names stay unique.

### ComfyUI box (batch or interactive)

```bash
cd infra
terraform apply \
  -var="run_id=broll-ep017" \
  -var-file="workloads/comfyui.tfvars"
```

### LoRA training box

```bash
terraform apply \
  -var="run_id=lora-channel-v3" \
  -var-file="workloads/lora_train.tfvars"
```

### Blender render box

```bash
terraform apply \
  -var="run_id=presenter-cycles-ep017" \
  -var-file="workloads/blender_render.tfvars"
```

### SSH without copying the IP

From the **repository root** (script lives in **`infra/`** next to Terraform):

```bash
chmod +x infra/verda_ssh.sh   # once
./infra/verda_ssh.sh
./infra/verda_ssh.sh -- tmux a -t comfyui   # optional remote command
```

From **`infra/`**:

```bash
./verda_ssh.sh
```

### Tear down (save money)

Use the **same** `-var` / `-var-file` pair you used for `apply` (Terraform needs identical inputs to locate the same resources):

```bash
terraform destroy \
  -var="run_id=broll-ep017" \
  -var-file="workloads/comfyui.tfvars"
```

**What survives `destroy`:** the **`verda_volume`** for `/mnt/models` stays in your Verda account unless you remove it from Terraform state/config. The **instance** and its **OS volume** go away (spot OS disks use `delete_permanently` per variable default).

---

## First boot: populating `/mnt/models`

The automation **creates directories** on the volume but does **not** download tens of GB of weights by default (slow, billable egress, and model choices change).

After the first `apply`, SSH in and follow the Hugging Face / ComfyUI model steps from `verda_workflow(2).md` — typical pattern:

```bash
sudo apt-get update && sudo apt-get install -y python3-pip git-lfs
pip install --user huggingface_hub
mkdir -p /mnt/models/checkpoints/ltx /mnt/models/checkpoints/wan /mnt/models/checkpoints/flux
# huggingface-cli download …  (see workflow doc for concrete repos)
```

Every future instance reuses the same volume → **no re-download**.

---

## File map (what each Terraform file does)

| File | Role |
|------|------|
| `versions.tf` | Terraform version floor + `required_providers` pin for `verda-cloud/verda`. |
| `provider.tf` | Declares `provider "verda" {}` and documents auth env vars. |
| `variables.tf` | All knobs (`workload`, `gpu_type`, `use_spot`, `run_id`, volume sizes, …). |
| `locals.tf` | Builds `hostname` + the **rendered** Verda startup script string. |
| `compute.tf` | The four `verda_*` resources (SSH key, volume, startup script, instance). |
| `outputs.tf` | `instance_ip`, `ssh_command`, volume id, reminders. |

---

## Startup script pipeline (how the shell pieces fit together)

`locals.tf` concatenates, in order:

1. Bash **strict mode** (`set -euo pipefail`) + logging to `/var/log/geopoai-bootstrap.log`.
2. `startup_scripts/lib_mount.sh` — defines `geopoai_mount_models_volume`.
3. A call to **`geopoai_mount_models_volume`** — discovers the first non-root block disk, `mkfs.ext4` + label **`geopoai-models`** on first use, mounts **`/mnt/models`**, writes **`fstab`** (`nofail`).
4. Workload body:
   - `comfyui` → `startup_scripts/comfyui_bootstrap.tftpl` (Terraform `templatefile` injects `geopoai_git_repo` + `comfyui_listen_port`).
   - `lora_train` → `startup_scripts/lora_bootstrap.sh`
   - `blender_render` → `startup_scripts/render_blender.sh`

If mounting fails (no secondary disk), the script logs a warning and continues so you can debug over SSH.

---

## Terraform state (do not ignore this)

`terraform.tfstate` is how Terraform remembers your Verda object IDs.

- **Solo quickstart:** keep the file local, back it up somewhere safe, and **do not** lose it.
- **Team / multiple machines:** configure a **remote backend** (see commented block in `versions.tf`) so everyone shares one state + locking.

This repo’s `infra/.gitignore` ignores **`.terraform/`** and crash logs. **`terraform.tfstate` is NOT ignored by default** so a solo developer can commit it if they want — but **never** commit secrets inside tfvars.

---

## Operational tips (from the workflow)

- **tmux first** after SSH — long jobs survive flaky Wi-Fi (`tmux a -t comfyui` for the ComfyUI session created by bootstrap).
- **Spot discipline:** checkpoint to `/mnt/models` every few minutes for training; batch renders frame-by-frame.
- **Daily habit:** glance at the Verda dashboard for stray instances.
- **Cost:** the **persistent volume is billed monthly** even when no VM runs — that is intentional (cheap vs re-download time).

---

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|----------------|---------------|
| `terraform validate` fails on resource fields | Provider schema changed | Registry docs vs `compute.tf` |
| SSH hangs / refused | Instance still booting / wrong key | Verda console + local `ssh -v` |
| ComfyUI not listening | Bootstrap failed mid-way | `/var/log/geopoai-bootstrap.log` on the VM |
| `/mnt/models` empty after boot | Volume not attached / wrong device | `lsblk`, Verda volume attachment UI |
| `destroy` wants to recreate unrelated things | Different `-var-file` / `run_id` than `apply` | Re-run with identical vars |

---

## Related documentation

- Narrative playbook + cost model: `verda_workflow(2).md`
- Map render pipeline (separate from Verda): `../CLAUDE.md`

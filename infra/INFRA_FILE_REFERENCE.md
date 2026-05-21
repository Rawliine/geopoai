# GeoPoAI `infra/` — file-by-file reference

This document stands alone: it describes **every file under `infra/`**, what each does in isolation, how they behave **as one system**, and explicit **non-goals** (what nothing here does for you).

Operator-oriented steps (apply, destroy, credentials) live in **`README.md`**. Narrative strategy and costs live in **`verda_workflow(2).md`**. This file is the **map of the machinery**.

---

## How the pieces fit together (system view)

1. **You** export Verda API credentials and run **`terraform apply`** with a **`run_id`** and a **`-var-file=workloads/…tfvars`** choice. Terraform talks to Verda’s API.
2. **`versions.tf` + `provider.tf`** pin the Terraform and provider versions and declare the Verda provider (no resources).
3. **`variables.tf`** defines every input knob (workload type, GPU, spot, volume sizes, optional git URL, etc.).
4. **`locals.tf`** turns variables into concrete strings: **hostname**, and the **full startup shell script** (wrapper + mount library + workload body).
5. **`compute.tf`** declares four Verda resources: **SSH key**, **persistent volume**, **startup script object**, **GPU instance** attached to the volume and script.
6. **Verda** creates the VM and runs the startup script **once on first boot**. The script mounts **`/mnt/models`** from the block volume, then runs ComfyUI / LoRA prep / Blender prep depending on **`workload`**.
7. **`outputs.tf`** exposes IP and hints after apply.
8. **`verda_ssh.sh`** (optional) reads **`terraform output`** and opens **`ssh ubuntu@<ip>`** from this directory.

**What this system does not do:** it does not auto-destroy when a job finishes, does not load `.env` for Terraform, does not download large model weights for you, does not enforce billing caps, and does not replace Verda’s dashboard for monitoring running VMs.

---

## Terraform files (root of `infra/`)

### `versions.tf`

**Alone:** Declares minimum Terraform version (`>= 1.5.0`) and the **`verda`** provider source/version constraint (`verda-cloud/verda`, `~> 1.0`). Contains a **commented example** of a remote S3 backend for shared state.

**Together:** Required so `terraform init` can download the correct provider binary. Without it, init either fails or uses wrong provider versions.

**Does not:** Define any cloud resources. Does not store secrets.

---

### `provider.tf`

**Alone:** A single `provider "verda" {}` block plus comments listing **`VERDA_CLIENT_ID`** and **`VERDA_CLIENT_SECRET`** as the auth mechanism.

**Together:** Activates the Verda provider for all `.tf` files in this directory.

**Does not:** Read `.env` automatically; you must export variables into the shell (or `source` a file yourself).

---

### `variables.tf`

**Alone:** Every **input variable** for the root module: `workload` (with validation: `comfyui` | `lora_train` | `blender_render`), `run_id`, `gpu_type`, `use_spot`, `location`, volume sizes/types, image slug, SSH public key path, optional `geopoai_git_repo`, ComfyUI port, `project_slug`, etc.

**Together:** All tunables for `compute.tf` / `locals.tf` without editing resource blocks. Workload-specific defaults are chosen via **`-var-file=workloads/…`**, not by editing this file per session.

**Does not:** Set `run_id` for you (passed at apply time in the documented workflow). Does not contain secrets.

---

### `locals.tf`

**Alone:** **Derived values:** default hostname prefix per `workload`, final `hostname`, the **Verda startup script name** (includes `run_id`), the **`mount_library`** file contents, the **workload body** (either `templatefile` for ComfyUI or `file()` for LoRA/Blender), and the final **`startup_script`** string by concatenating bash preamble + mount lib + `geopoai_mount_models_volume` call + body.

**Together:** This is where **“which bash runs on the VM”** is assembled. Changing workload behavior for ComfyUI usually means editing **`startup_scripts/comfyui_bootstrap.sh`** and/or **`locals.tf`** wiring.

**Does not:** Run at apply time on your laptop (only **renders** a string for the Verda API). Does not execute shell on your machine.

---

### `compute.tf`

**Alone:** Four **`resource`** blocks:
- **`verda_ssh_key.this`** — uploads your public key (from `ssh_public_key_path`) to Verda.
- **`verda_volume.models`** — persistent block volume for `/mnt/models`.
- **`verda_startup_script.this`** — uploads `local.startup_script` text to Verda.
- **`verda_instance.this`** — VM with `instance_type`, `image`, `hostname`, `location`, `is_spot`, keys, startup script id, `existing_volumes`, `os_volume` map (size, type, spot discontinue behavior).

**Together:** This is the **entire Verda footprint** for this module: one key, one data volume, one script object, one instance. `terraform destroy` with the same variables removes the **instance** (and OS disk per policy) but **keeps** the volume unless you remove it from config/state.

**Does not:** Guarantee field names match the current provider (validate against registry docs if `plan`/`apply` errors). Does not create multiple instances or autoscaling groups.

---

### `outputs.tf`

**Alone:** Outputs: `workload`, `hostname`, `instance_ip`, `ssh_command`, `models_volume_id`, `reminder` (string about destroy + volume).

**Together:** Feeds **`verda_ssh.sh`** and human copy-paste workflows after apply.

**Does not:** Mark outputs as sensitive (IP is not a secret, but it is infrastructure detail). Does not open SSH for you.

---

## Shell helper (root of `infra/`)

### `download_models.sh`

**Alone:** Idempotent Hugging Face download script for `/mnt/models` (LTX, Wan, FLUX, LoRAs); verifies file sizes; writes `.geopoai_download_complete`.

**Together:** Called from `startup_scripts/comfyui_bootstrap.sh` on first launch (and via `repair_comfyui_setup.sh`).

**Does not:** Run without `HF_TOKEN`; does not install ComfyUI.

---

### `scripts/fetch_reference_workflows.sh`

**Alone:** Maintainer script to refresh `broll/comfyui_workflows/reference/*.json` from upstream GitHub.

**Together:** Optional; not run on the instance automatically.

---

### `verda_ssh.sh`

**Alone:** Bash script: `cd` to the directory containing the script (must be **`infra/`** where `.tf` and state live), runs **`terraform output -raw instance_ip`**, then **`exec ssh … ubuntu@$IP`**, with optional remote command arguments and `accept-new` / keepalive SSH options.

**Together:** Avoids manually copying IP from UI or outputs. **Requires** Terraform CLI and a state that already has **`instance_ip`**.

**Does not:** Run `terraform apply`. Does not load `.env`. Does not work if you run Terraform from another directory with a different backend path unless state still resolves (standard is run from `infra/`).

---

## `workloads/*.tfvars`

### `workloads/comfyui.tfvars`

**Alone:** Sets `workload = "comfyui"`, default `gpu_type`, `use_spot`, optional `geopoai_git_repo`, comments.

**Together:** Selects ComfyUI bootstrap path in `locals.tf` when passed as **`-var-file`**.

**Does not:** Set `run_id` (CLI in the documented workflow).

---

### `workloads/lora_train.tfvars`

**Alone:** Sets `workload = "lora_train"`, GPU/spot defaults for training-oriented use.

**Together:** Same Terraform code as ComfyUI; different **body script** (`lora_bootstrap.sh`).

**Does not:** Install ai-toolkit or run training (manual after SSH per playbook).

---

### `workloads/blender_render.tfvars`

**Alone:** Sets `workload = "blender_render"`, GPU/spot defaults for Blender batch use.

**Together:** Selects **`render_blender.sh`** body (apt install Blender, output dirs).

**Does not:** Upload `.blend` files or run renders (you do that after SSH/rsync).

---

## `startup_scripts/` (source for the Verda boot script)

These files are **read by Terraform** (`file()` / `templatefile()`) and **never executed on your laptop** by Terraform. They become the **`script`** payload on **`verda_startup_script`**.

### `startup_scripts/lib_mount.sh`

**Alone:** Bash **function library** (no shebang): finds a non-root block device, optionally `mkfs.ext4` with label **`geopoai-models`**, mounts **`/mnt/models`**, updates **`fstab`**, creates standard subdirectories, `chown`s to `ubuntu`.

**Together:** Prepended logically before workload-specific steps; **`locals.tf`** calls **`geopoai_mount_models_volume`** after sourcing the function definitions.

**Does not:** Install ComfyUI or Blender. Does not download models.

---

### `startup_scripts/comfyui_bootstrap.sh`

**Alone:** Terraform **template** (ComfyUI workload only): apt packages, clone ComfyUI, Python venv, `pip install -r requirements.txt`, symlinks under `ComfyUI/models` → `/mnt/models/...`, optional GeoPoAI clone from `geopoai_git_repo`, starts **`tmux`** session **`comfyui`** listening on **`0.0.0.0:${comfyui_listen_port}`**.

**Together:** This is the **automation** that makes the instance ready for ComfyUI after boot (modulo first-time pip latency).

**Does not:** Pin exact PyTorch/CUDA wheels beyond what ComfyUI’s `requirements.txt` does. Does not secure ComfyUI with auth (listen is wide open by design; use SSH tunnel or firewall as needed).

---

### `startup_scripts/lora_bootstrap.sh`

**Alone:** Installs dev-ish packages (`git`, `python3`, `tmux`, `nvtop`, build tools, etc.) and prints “next steps” hints.

**Together:** Minimal training box; you install training frameworks after SSH.

**Does not:** Run training jobs.

---

### `startup_scripts/render_blender.sh`

**Alone:** `apt install`s **Blender** and helpers, creates **`/home/ubuntu/outputs`** and **`~/renders`**, prints readiness.

**Together:** Blender render **environment** only.

**Does not:** Run `blender --background` for your project automatically.

---

## Documentation and meta

### `README.md`

**Alone:** Human operator guide: credentials, apply/destroy examples, state guidance, troubleshooting, pointer to provider docs.

**Together:** Entry point for **how to run** this stack.

**Does not:** Replace this file’s per-file inventory (that’s **`INFRA_FILE_REFERENCE.md`**).

---

### `INFRA_FILE_REFERENCE.md`

**Alone:** This document — a directory map: each file’s role, how they compose, and explicit non-goals.

**Together:** Complements **`README.md`** (procedures) and **`verda_workflow(2).md`** (strategy); use it when onboarding or refactoring Terraform/shell layout.

**Does not:** Define Verda API fields (see provider registry) or guarantee pricing.

---

### `verda_workflow(2).md`

**Alone:** Long-form personal playbook: strategy, costs, when to use spot, ComfyUI mental model, optional Claude/Blender iteration notes, example snippets (some may drift from committed Terraform).

**Together:** Explains **why** this `infra/` layout exists.

**Does not:** Authoritatively define Terraform schema (trust **`compute.tf`** + provider registry).

---

### `.gitignore`

**Alone:** Ignores **`.terraform/`**, crash logs, `*.tfstate.backup`, lock metadata patterns, optional secret tfvars names.

**Together:** Keeps local Terraform clutter and backups out of git.

**Does not:** Ignore `terraform.tfstate` by default (solo devs may commit it; remote backend is still preferred for teams—see `README.md`).

---

## Explicit non-goals (nothing in `infra/` does these)

| Concern | Who / what actually handles it |
|--------|----------------------------------|
| Billing caps & budget alerts | Verda account / billing UI + your discipline |
| Auto-destroy when ComfyUI queue empty | You add a driver script or CI (not in repo) |
| Loading `.env` for Terraform | Your shell, `direnv`, or manual `export` |
| Downloading model weights | [`download_models.sh`](download_models.sh) on first comfyui boot (`huggingface_token` + `geopoai_git_repo` required) |
| High availability / multi-node | Out of scope (single `verda_instance`) |
| Verda API schema correctness over time | Pin provider version + run `terraform validate` / `plan` after upgrades |

---

## Quick dependency diagram (mental)

```text
variables.tf + workloads/*.tfvars
        │
        ▼
locals.tf ──────────────► startup_scripts/*  (read as text)
        │
        ▼
compute.tf ──► Verda API ──► VM + volume + script
        │
        ▼
outputs.tf ──► verda_ssh.sh (optional)
```

If a single file should be updated for a behavior change:

| Change | Likely file(s) |
|--------|----------------|
| New Terraform input | `variables.tf`, maybe `locals.tf` / `compute.tf` |
| Different Verda resource fields | `compute.tf` |
| Mount path / disk detection | `startup_scripts/lib_mount.sh` |
| ComfyUI install / tmux / symlinks | `startup_scripts/comfyui_bootstrap.sh` |
| Repair failed bootstrap on live VM | `repair_comfyui_setup.sh` → `scripts/resume_bootstrap_on_vm.sh` |
| Shared apply/SSH helpers | `lib/geopoai_common.sh` |
| Default GPU/spot per workload | `workloads/*.tfvars` |
| Post-apply IP / new output | `outputs.tf` |
| Terraform / provider version | `versions.tf` |

---

*Last implied layout: all paths relative to repository root `GeoPoAI/infra/`.*

# GeoPoAI → Verda infrastructure (Terraform)

This directory turns the personal playbook in `OPERATOR_RUNBOOK.md` into **repeatable, versioned infrastructure**: one persistent **block volume** for models/LoRAs/datasets, and **ephemeral GPU instances** you bring up for batches and destroy when idle.

If you only read one section: **Credentials → First apply → SSH → Destroy**.

**Per-file map of this directory** (what each file does alone vs as a system): **`INFRA_FILE_REFERENCE.md`**.

---

## What you get

| Piece | Purpose |
|-------|---------|
| `verda_ssh_key` | Registers your laptop’s **public** SSH key with Verda once. |
| `verda_volume` | **Persistent** NVMe volume at **`/mnt/models`** (survives **instance** destroy via `destroy_comfyui_instance.sh`; `prevent_destroy` blocks accidental full destroy). |
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
4. **SSH key pair** on your laptop; by default Terraform reads **`~/.ssh/id_ed25519.pub`** (override with `ssh_public_key_path`, e.g. `~/.ssh/id_rsa.pub`).

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

Always pass a fresh **`run_id`** per **VM session** so hostnames and OS volume names stay unique. The **models volume name is fixed** (`geopoai-models-persistent`) — only the ephemeral instance/OS disk changes with `run_id`.

### GPU session manager (`pipeline/gpu_session.py`) — recommended

A Python entry point wraps the terraform ceremony below: **up → health → use → auto-down**,
with a best→worst GPU fallback chain (live Verda availability), an idle/budget **watchdog**, and a
VM-side **dead-man** cron backstop. Workloads are declared in `infra/sessions.json`; laptop session
state lives in `infra/.session_state.json` (gitignored). Needs `VERDA_CLIENT_ID` / `VERDA_CLIENT_SECRET`
in the repo-root `.env`.

```bash
python pipeline/gpu_session.py gpus --all-locations          # browse live free SKUs
python pipeline/gpu_session.py interactive comfyui_setup     # wizard: pick GPU/region/spot, deploy
python pipeline/gpu_session.py up comfyui --verbose          # automated best→worst fallback
python pipeline/gpu_session.py status comfyui                # state, health, uptime, est. cost
python pipeline/gpu_session.py watchdog comfyui              # idle/budget auto-down (laptop side)
python pipeline/gpu_session.py down comfyui                  # destroy INSTANCE only (volume kept)
python pipeline/gpu_session.py destroy volume                # delete models volume (typed confirm)
```

`down` / `destroy instance` only ever target `verda_instance.this` — the models volume is unreachable
from this tool by construction. The legacy `*.sh` scripts below remain valid fallbacks. Full reference:
**`OPERATOR_RUNBOOK.md` → "Session manager"**.

### `run_id` naming — what each means

| `run_id` example | When to use | Var-files | Notes |
|------------------|-------------|-----------|--------|
| `setup-001`, `setup-002`, … | **First-time (or re-) download** of weights to `/mnt/models` | `comfyui.tfvars` only | Use `./apply_comfyui_setup.sh`. Increment suffix if you destroyed state/volume and start over (`setup-002` ≠ “phase 2” — it’s just the **second setup attempt**). |
| `broll-test-001`, `dev-comfy-0423`, … | **Iteration** — workflow tuning, a few smoke shots | `comfyui.tfvars` ± production | Any label you like; new `run_id` per VM. Same persistent volume if Terraform state still has it. |
| `broll-ep017`, `broll-ep018`, … | **Production batch** for episode 17, 18, … | `comfyui.tfvars` + `comfyui_production.tfvars` | One `run_id` per episode session (or per overnight batch). H100 spot. Destroy with `./destroy_comfyui_instance.sh broll-ep017 --production`. |

**Not special to Terraform:** `setup-001` and `setup-002` are arbitrary strings — the repo uses `setup-*` by convention for download runs, `broll-ep*` for episode inference. What matters is **which var-files you pass**, not the prefix alone.

### ComfyUI — setup (first boot: download models)

**Why you see no output in the local terminal:** `terraform apply` only creates the VM. Install + model downloads run **on the server** via Verda’s startup script (`/var/log/geopoai-bootstrap.log`). Stream that log over SSH (below).

**Recommended (handles delayed IP + optional live log):**

```bash
cd infra
chmod +x apply_comfyui_setup.sh destroy_comfyui_instance.sh repair_comfyui_setup.sh wait_for_instance_ip.sh verda_ssh.sh
./apply_comfyui_setup.sh setup-001
```

This runs `terraform apply`, polls until `instance_ip` exists, then tails the bootstrap log. Use `--no-watch` to stop after the IP is ready; use `--apply-only` for apply alone.

**Bootstrap failed on an existing VM** (e.g. old startup script): re-run install over SSH; **`repair_comfyui_setup.sh` rsyncs your local checkout** (no GitHub login on the VM):

```bash
./repair_comfyui_setup.sh setup-001 --watch
```

If repair finished but logs show `skip model download`, run downloads only:

```bash
./download_models_on_vm.sh setup-001
```

`./verda_ssh.sh` waits for an IP automatically (reads `run_id` / `workload` from Terraform outputs).

Bootstrap often takes **1–3 hours**.

When downloads finish, tear down the **instance only** (models volume stays):

```bash
./destroy_comfyui_instance.sh setup-001
```

**Do not run bare `terraform destroy`** — it attempts to delete the persistent volume too (see [Tear down](#tear-down-save-money)).

### ComfyUI — GPU phases (setup → iteration → production)

There is **no automatic GPU switch**. You change phase by which var-files you pass to `terraform apply` and by using a new `run_id` per VM session.

| Phase | Command | GPU (typical) | When |
|-------|---------|---------------|------|
| **Setup** | `./apply_comfyui_setup.sh setup-001` | V100 on-demand (`comfyui.tfvars` only) | Once: download ~200 GiB to `/mnt/models` |
| **Iteration** | `terraform apply -var=run_id=... -var-file=comfyui.tfvars` [± production] | Your choice | Tune `broll/comfyui_workflows/`, smoke shots |
| **Production** | `terraform apply` with **both** `comfyui.tfvars` + `comfyui_production.tfvars` | H100 spot | Batch AI generation |

Between any phase: **`./destroy_comfyui_instance.sh <run_id>`** (add `--production` if that apply used production tfvars). The block volume `geopoai-models-persistent` stays attached in Terraform state.

### ComfyUI — production batch (after setup)

```bash
terraform apply \
  -var="run_id=broll-ep017" \
  -var-file="workloads/comfyui.tfvars" \
  -var-file="workloads/comfyui_production.tfvars"
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

**Use the helper — not bare `terraform destroy`:**

```bash
chmod +x destroy_comfyui_instance.sh   # once
./destroy_comfyui_instance.sh setup-001
./destroy_comfyui_instance.sh broll-ep017 --production
```

This runs `terraform destroy -target=verda_instance.this` only. The **models volume** has `lifecycle { prevent_destroy = true }` in `compute.tf` so a mistaken full destroy fails instead of deleting ~200 GiB.

| Command | Instance + OS disk | Models volume (`geopoai-models-persistent`) |
|---------|-------------------|---------------------------------------------|
| `./destroy_comfyui_instance.sh <run_id>` | **Removed** | **Kept** (still billed monthly) |
| `terraform destroy` (full) | Removed | **Blocked** by `prevent_destroy` (do not remove that guard casually) |
| Delete volume on purpose | — | Remove `prevent_destroy`, then `terraform destroy -target=verda_volume.models` |

**If you already ran full `terraform destroy`:** Import the restored volume before apply:

```bash
terraform import -var="run_id=broll-test-001" -var-file=workloads/comfyui.tfvars \
  verda_volume.models <volume-id-from-dashboard>
```

Then `terraform apply` with the same vars (+ production tfvars if needed). If plan wanted to **replace** the volume because of `location`, `compute.tf` uses `ignore_changes = [location]` on the volume so import + apply attaches without wiping weights.

Historical setup-001 volume: id `a4e5300f-32c3-41f4-9a74-d057fb7d628f`, name `geopoai-models-persistent`.

---

## First launch (fully automated model download)

**Volume size:** default **280 GB** (`models_volume_size_gb`) — LTX dev fp8 + Wan 14B T2V/I2V + FLUX.2 Comfy repack + LoRAs + headroom.

Before the first `terraform apply` for ComfyUI:

1. Accept Hugging Face licenses for [Lightricks/LTX-2.3](https://huggingface.co/Lightricks/LTX-2.3) and [Lightricks/LTX-2.3-fp8](https://huggingface.co/Lightricks/LTX-2.3-fp8) (and any other gated repos you enable).
2. Create a HF **read** token.
3. In [`workloads/comfyui.tfvars`](workloads/comfyui.tfvars) set:
   - `geopoai_git_repo` — SSH or HTTPS URL to this repo (bootstrap clones it for workflows + `download_models.sh`).
   - `huggingface_token` — or pass `-var="huggingface_token=hf_..."` at apply time.
4. **`comfyui.tfvars`** is already tuned for setup (`1L40S.20V`, `use_spot = false`). Put `TF_VAR_huggingface_token=hf_…` in `.env` and `source` it before apply.

```bash
cd infra
set -a && source ../.env && set +a
terraform apply \
  -var="run_id=setup-001" \
  -var-file="workloads/comfyui.tfvars"
```

Bootstrap will: install ComfyUI + custom nodes (LTXVideo, VHS, GGUF, KJNodes), symlink `/mnt/models`, run [`download_models.sh`](download_models.sh) once (writes `.geopoai_download_complete`), copy `broll/comfyui_workflows/` to the volume, start ComfyUI in tmux.

Monitor: `./verda_ssh.sh -- tail -f /var/log/geopoai-bootstrap.log` (1–3 hours typical).

Re-run downloads manually if needed:

```bash
sudo -u ubuntu HF_TOKEN=hf_… bash /home/ubuntu/GeoPoAI/infra/download_models.sh
```

Subsequent applies skip download when the marker file exists.

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
2. `lib_user.sh` → `geopoai_ensure_login_user` (creates `ubuntu` on images that only have `root`).
3. `lib_mount.sh` → **`geopoai_mount_models_volume`** — secondary disk → **`/mnt/models`**.
4. Env exports (`GEOPOAI_GIT_REPO`, `HF_TOKEN`, SSH public key line) + `lib_ssh_access.sh`.
5. Workload body:
   - `comfyui` → `lib_apt_comfyui.sh` + `comfyui_bootstrap.sh` (plain bash; same script used by `repair_comfyui_setup.sh`).
   - `lora_train` → `lora_bootstrap.sh`
   - `blender_render` → `render_blender.sh`

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

### Storage you are provisioning (monthly vs hourly)

| Disk | Terraform | Size default | Type | Billed | Typical use |
|------|-----------|--------------|------|--------|-------------|
| **Models volume** | `verda_volume.models` | **280 GB** | **NVMe** block | **~$0.10/GB/month** (~**$28/mo** for 280 GB) while it exists | LTX + Wan + FLUX weights — **survives instance destroy** (`destroy_comfyui_instance.sh`) |
| **OS / boot disk** | `verda_instance` → `os_volume` | **100 GB** | **NVMe** | With the **running instance** (ephemeral) | ComfyUI install, venv, `~/GeoPoAI` clone — **gone on destroy** |

Setup on **L40S on-demand** is mostly **GPU hourly** (~$1.36/h in FIN — check dashboard) for a few hours, plus the **ongoing models volume** once Terraform creates it. After setup, destroy the VM; you still pay for the **280 GB** block volume until you delete it in Verda/Terraform.

GPU **spot** savings apply only when you apply with `comfyui_production.tfvars` (H100 + spot).

---

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|----------------|---------------|
| `terraform validate` fails on resource fields | Provider schema changed | Registry docs vs `compute.tf` |
| SSH hangs / refused | Instance still booting / wrong key | Verda console + local `ssh -v` |
| ComfyUI not listening | Bootstrap failed mid-way | `/var/log/geopoai-bootstrap.log` on the VM |
| `/mnt/models` empty after boot | Volume not attached / wrong device | `lsblk`, Verda volume attachment UI |
| `503: Not enough resources` on apply | No free GPUs of that type in `location` | Set `location` in `comfyui.tfvars` to the region where the dashboard shows capacity (e.g. **FIN-01** vs FIN-03). Instance and `verda_volume.models` **must** use the same `location`. Change `gpu_type` to a SKU that is actually free there. |
| `400: Operating system is not valid for this instance type` | `verda_image` not in that GPU’s `supported_os` list | Query: `GET https://api.verda.com/v1/instance-types` (auth via OAuth) and find `supported_os` for your `gpu_type`. Example: **V100** → `ubuntu-22.04-cuda-12.4-docker`; **H100 / RTX PRO** → `ubuntu-24.04-cuda-13.0-open-docker`. |
| Apply “failed” but instance exists; no IP in outputs | Verda sets `ip` after create; old `ssh_command` output crashed apply | Use `./apply_comfyui_setup.sh` or `./wait_for_instance_ip.sh` then `./verda_ssh.sh`. Outputs are null-safe in `outputs.tf`. |
| `Permission denied (publickey)` on SSH | Wrong key, or logging in as `ubuntu` when only `root` has keys | `verda_ssh.sh` tries `ubuntu` then **`root`**. Or `GEOPOAI_SSH_USER=root ./verda_ssh.sh`. Use `-i ~/.ssh/id_ed25519`. |
| Bootstrap: `invalid user ubuntu` | Image has no `ubuntu` account (e.g. `ubuntu-22.04-cuda-12.4-docker`) | `lib_user.sh` creates `ubuntu` at boot. Stuck VM: `./repair_comfyui_setup.sh <run_id>`. |
| Bootstrap: `Unable to locate package numfmt` | `numfmt` is not an apt package (it is in `coreutils`) | Fixed in bootstrap v5. Stuck VM: `./repair_comfyui_setup.sh <run_id> --watch`. |
| Ran `terraform apply` then SSH immediately | Verda IP and SSH lag behind apply | Use `./apply_comfyui_setup.sh` (waits + tails log). `./verda_ssh.sh` polls for IP from Terraform outputs. |
| `destroy` wants to recreate unrelated things | Different `-var-file` / `run_id` than `apply` | Re-run with identical vars |
| Accidentally deleted models volume | Ran bare `terraform destroy` before `prevent_destroy` | Dashboard: search volume id/name above; else re-setup + download |
| `prevent_destroy` blocks full destroy | Intentional guard on `verda_volume.models` | Use `./destroy_comfyui_instance.sh` only |

---

## Related documentation

- Narrative playbook + cost model: `OPERATOR_RUNBOOK.md`
- Map render pipeline (separate from Verda): `../CLAUDE.md`

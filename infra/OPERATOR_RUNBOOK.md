# Verda Workflow + Claude Code 3D Iteration Guide

Personal reference. Practical, opinionated, optimized for low idle cost and fast iteration. Not project documentation — this is yours.

**Terraform layout for this repo:** see `infra/README.md` (variables, apply/destroy commands, startup script pipeline).

---

## Quick mental model

Verda is a specialized AI/ML cloud provider (formerly DataCrunch). You rent GPU machines by the hour. Two questions decide everything:

1. **Does the workload fit on my RTX 3070 Ti (8GB VRAM) locally?** If yes, run it locally — free.
2. **If not, does the job batch cleanly so I can spin up Verda, run it, and tear down?** If yes, use spot pricing on Verda — cheap.

That's the whole game. Don't leave instances running idle.

**Local (your laptop):**
- All Blender authoring + preview renders (Eevee fits easily in 8GB)
- Mapbox/Playwright pipeline (already done)
- Manim renders at preview quality
- Stock B-roll fetching (network-bound, CPU-only)
- TTS generation (CPU or small GPU)
- Schema validation, orchestration testing
- Final composition (ffmpeg)
- Everything Claude Code touches during normal iteration

**Verda (rent, batch, tear down):**
- AI video generation (LTX-2.3 needs 32GB VRAM — won't fit on your 3070 Ti)
- Wan 2.2 generation (same constraint)
- FLUX image generation (won't fit comfortably either)
- LoRA training (multi-hour heavy jobs)
- Final-quality Cycles renders for the presenter (long batch jobs)

---

## The Verda product map — what each item in the dashboard is, and what you use

### Compute services

**Instances** — single VMs with one or more GPUs. SSH in, install what you want, run jobs, destroy. The most flexible option and what you'll use 95% of the time. Lifecycle: create → SSH in → run → destroy (or hibernate).

**Instant Clusters** — multi-node GPU setups wired with InfiniBand. For distributed training across many GPUs. **You don't need this.** Single instances cover everything in your project.

**Containers (Serverless Containers + Batch Jobs)** — you push a Docker image, Verda runs it on a GPU and scales to zero when idle. Two flavors: *auto-scaling containers* (for serving inference under variable load) and *batch jobs* (for one-shot processing). **Useful later** once you have steady orchestrator-driven traffic. Skip during early development.

**Managed Endpoints** — Verda-hosted APIs for popular models (FLUX.2, FLUX.1 Kontext, Whisper). Pay-per-output, no infrastructure. **Skip.** Self-hosted on your own instance gives you LoRA support, free image generation on instances you're already running, and full ComfyUI control. Managed endpoints make sense only if you're not running an instance and need a single image at 3am — which isn't your pattern.

### Storage

**Block Volumes** — attached disks that persist when instances are destroyed. **Critical.** Use this for model weights (LTX-2.3 ~20GB, Wan 2.2 ~30GB, FLUX ~25GB, LoRAs). Attach to whatever instance is currently running, never re-download. ~$0.10/GB/month.

**Shared File Systems** — like block volumes but multiple instances can mount simultaneously. **Skip** — you run single instances.

### Other

**Container Registries** — private Docker image storage. Only matters if you go the Containers route later.

**Credentials** — OAuth API credentials (client_id + client_secret). This is how Terraform and your scripts talk to Verda. Generate one early. Project page → Keys → Cloud API Credentials → Create. Save the secret somewhere safe; it won't be shown again.

**Team** — collaborator management. Solo project: ignore.

**Billing** — balance, charges, budget alerts. Configure budget alerts here *before* doing anything else.

**Settings** — preferences, region, 2FA. Default region is fine (Finland — FIN-01 or FIN-03).

---

## Account setup checklist

Do these in order, once:

1. Sign up at verda.com. Upload your SSH public key in Settings.
2. **Set a hard budget alert** in Billing. If you've committed $300, alert at $250, hard stop at $290. Compute bills can run away overnight.
3. Go to Keys → Cloud API Credentials → Create. Save the `client_id` and `client_secret` to your password manager. These authenticate Terraform and the Python SDK.
4. Install Terraform locally (`brew install terraform` on macOS, package manager on Linux). Or OpenTofu (`brew install opentofu`) — it's a drop-in replacement that's MPL-licensed.
5. (Optional) Install the Verda Python SDK: `pip install verda` (or whatever the current package name is on PyPI — check their GitHub `verda-cloud/sdk-python`).

---

## Spot vs on-demand — how it actually works

Two pricing models, same hardware.

**On-demand (Pay As You Go)** — you reserve the GPU, it's yours until you destroy the instance. Charged at full advertised rate, billed in 10-minute increments. Predictable, can't be interrupted.

**Spot** — you rent unused capacity at a discount. **At least 25% cheaper than on-demand**, often much more in practice (H100 SXM5 is $0.80/h spot vs $2.29/h on-demand — about 65% off). Same 10-minute billing increments. **Can be terminated at any time without warning** if Verda needs the capacity for an on-demand customer.

**Important detail:** spot is **only available on Instances and Serverless Containers.** Clusters and Bare-metal don't offer spot. Managed Endpoints have their own pay-per-output model.

### Where to find the spot toggle

It's not a separate menu — it's a checkbox/option when you create an instance.

- **Web console:** when launching an instance, look for "Spot Pricing" toggle or radio button on the creation form. Same hardware list, different price column.
- **Terraform:** boolean field on the instance resource (`is_spot = true`).
- **Python SDK / API:** boolean `is_spot` field on instance creation.

### When to pick which

| Workload | Spot or on-demand? | Why |
|---|---|---|
| Video generation batch (30+ clips) | Spot | Interruption just delays the batch; checkpoint between clips |
| ComfyUI interactive iteration | On-demand | You're sitting there waiting |
| LoRA training (8-15hr) | Spot, with checkpointing every ~30min | Long job, must checkpoint |
| Blender Cycles batch render | Spot | Frames are independent; lost work is one frame |
| Quick debugging session | On-demand cheapest available GPU | A6000 or L40S, ~$0.50-1/h |

**Key for spot reliability:** checkpoint discipline. Any batch job writes intermediate state to your block volume every few minutes. If the spot instance dies, the next instance picks up where it stopped.

In practice, spot interruptions on Verda are reasonably uncommon for short jobs (under a few hours). Long training jobs are where interruption hits hardest, and that's exactly where you have checkpointing anyway.

---

## The unified ComfyUI instance pattern

This is the corrected approach: **one instance with everything baked in.**

```
Instance: 1x H100 SXM5 spot ($0.80/h)
├── ComfyUI server
├── /mnt/models/ (block volume, ~100GB persistent)
│   ├── ltx-2.3/         ← video generation
│   ├── wan-2.2/         ← video generation, face-heavy shots
│   ├── flux-2-dev/      ← image generation (keyframes, illustrations)
│   ├── loras/
│   │   ├── soft_enhance_style.safetensors
│   │   ├── channel_aesthetic_v3.safetensors  ← your trained LoRAs
│   │   └── owl_character_v1.safetensors
│   └── workflows/
│       ├── ltx_text_to_video.json
│       ├── ltx_image_to_video.json
│       ├── wan_text_to_video.json
│       ├── flux_text_to_image.json
│       └── flux_then_ltx_keyframe_to_video.json
└── Your code repo (cloned at boot from startup script)
```

Why this works:
- The block volume persists across instance lifecycles. Spin up new instance → attach volume → ComfyUI starts in seconds with all models present.
- One ComfyUI workflow can chain FLUX → LTX (image-to-video) without shuttling files between services.
- LoRAs you train get used immediately by everything — same instance.
- When the instance is running for a video batch, image generation is essentially free (GPU-hour already paid for).
- Spot pricing applies — single H100 at $0.80/h.

---

## Terraform setup — the real way

Verda has a first-class Terraform provider (`verda-cloud/verda`). This replaces the fake `verda-cli` scripting I sketched earlier. Provider supports instances, volumes, SSH keys, startup scripts. Doesn't yet support Instant Clusters or Serverless Containers (which you don't need).

### Repo structure

In your GeoPoAI repo:

```
GeoPoAI/
└── infra/
    ├── main.tf                  # provider config + instance definitions
    ├── variables.tf             # parameterize GPU type, spot toggle, etc.
    ├── startup_scripts/
    │   ├── comfyui_bootstrap.sh # installs/starts ComfyUI on boot
    │   └── render_blender.sh    # for Blender render boxes
    ├── workloads/
    │   ├── comfyui.tfvars       # vars for the ComfyUI box
    │   ├── lora_train.tfvars    # vars for LoRA training box
    │   └── blender_render.tfvars
    └── README.md
```

### `main.tf` example

```hcl
terraform {
  required_providers {
    verda = { source = "verda-cloud/verda", version = "~> 1.0" }
  }
}

provider "verda" {
  # reads VERDA_CLIENT_ID and VERDA_CLIENT_SECRET from env
}

# SSH key — defined once, reused across instances
resource "verda_ssh_key" "main" {
  name       = "primary"
  public_key = file("~/.ssh/id_rsa.pub")
}

# Persistent volume for models — survives across instance destroys
resource "verda_volume" "models" {
  name     = "models-persistent"
  size     = 200  # GB
  type     = "NVMe"
  location = "FIN-03"
}

# Bootstrap script that installs ComfyUI on first boot, attaches the volume
resource "verda_startup_script" "comfyui" {
  name   = "comfyui-bootstrap"
  script = file("${path.module}/startup_scripts/comfyui_bootstrap.sh")
}

# The instance itself
resource "verda_instance" "comfyui" {
  instance_type     = var.gpu_type            # e.g., "1H100.80S.30V"
  image             = "ubuntu-24.04-cuda-13.0-open-docker"
  hostname          = "comfyui-${var.run_id}"
  location          = "FIN-03"
  is_spot           = var.use_spot            # true for batch
  ssh_key_ids       = [verda_ssh_key.main.id]
  startup_script_id = verda_startup_script.comfyui.id
  existing_volumes  = [verda_volume.models.id]

  os_volume = {
    name = "comfyui-os-${var.run_id}"
    size = 100
    type = "NVMe"
    # cleanup OS volume if spot evicts us
    on_spot_discontinue = "delete_permanently"
  }
}

output "instance_ip" {
  value = verda_instance.comfyui.ip
}

output "ssh_command" {
  value = "ssh ubuntu@${verda_instance.comfyui.ip}"
}
```

### `variables.tf`

```hcl
variable "gpu_type" {
  description = "Verda instance type, e.g. 1H100.80S.30V"
  type        = string
  default     = "1H100.80S.30V"
}

variable "use_spot" {
  description = "Use spot pricing"
  type        = bool
  default     = true
}

variable "run_id" {
  description = "Unique identifier for this run"
  type        = string
}
```

### Bringing it up

```bash
export VERDA_CLIENT_ID="your-id"
export VERDA_CLIENT_SECRET="your-secret"

cd infra
terraform init   # once, downloads the provider

# bring up a ComfyUI instance for a batch
terraform apply -var="run_id=broll-ep017" -var-file="workloads/comfyui.tfvars"

# wait for it to be ready, then
ssh ubuntu@$(terraform output -raw instance_ip)
# ... do your work in tmux ...

# tear down
./destroy_comfyui_instance.sh broll-ep017 --production
```

Note: use **`./destroy_comfyui_instance.sh <run_id>`** — not bare `terraform destroy`. The helper runs `terraform destroy -target=verda_instance.this` only. The models volume has `prevent_destroy` in `compute.tf` so full destroy cannot wipe weights by mistake.

### Why Terraform over the Python SDK or web UI

- **Reproducible.** Same .tf file = same setup every time. No "wait what did I configure last time."
- **Version-controlled.** Infrastructure changes go through git like code.
- **Declarative.** "I want an instance with these properties." Not "click these buttons in order."
- **One-line provisioning.** `terraform apply` is the whole workflow.

The Python SDK is for cases where Python code needs to dynamically provision (e.g., your orchestrator spinning up instances on demand). For your standard "bring up, batch, tear down" workflow, Terraform is cleaner.

---

## Startup script — what runs on boot

`infra/startup_scripts/comfyui_bootstrap.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Mount the models volume (first attached non-OS device)
MODELS_DEV=$(lsblk -nlo NAME,TYPE | grep disk | awk '{print "/dev/"$1}' | grep -v $(findmnt -n -o SOURCE / | sed 's|[0-9]*$||') | head -1)
mkdir -p /mnt/models
mount $MODELS_DEV /mnt/models || (mkfs.ext4 -F $MODELS_DEV && mount $MODELS_DEV /mnt/models)
echo "$MODELS_DEV /mnt/models ext4 defaults 0 0" >> /etc/fstab

# Clone code repo (uses agent-forwarded SSH or a deploy key)
sudo -u ubuntu bash -c '
  cd ~
  if [ ! -d GeoPoAI ]; then
    git clone git@github.com:youruser/GeoPoAI.git
  else
    cd GeoPoAI && git pull
  fi
'

# Symlink models from persistent volume into ComfyUI dirs
sudo -u ubuntu bash -c '
  cd ~/ComfyUI/models
  rm -rf checkpoints loras
  ln -sf /mnt/models/checkpoints checkpoints
  ln -sf /mnt/models/loras loras
'

# Start ComfyUI in a tmux session so it survives SSH disconnects
sudo -u ubuntu bash -c '
  tmux new-session -d -s comfyui "cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188"
'

# Tail the log so the user can see startup status
tail -f /home/ubuntu/ComfyUI/comfyui.log 2>/dev/null &

echo "Bootstrap complete. ComfyUI starting on port 8188."
```

First time you ever boot an instance, you need to populate the models volume manually:

```bash
# SSH in to a fresh instance, then:
cd /mnt/models
mkdir -p checkpoints/ltx checkpoints/wan checkpoints/flux loras workflows

# Download models — one-time
huggingface-cli download Lightricks/LTX-Video --local-dir checkpoints/ltx
huggingface-cli download Wan-AI/Wan-2.2 --local-dir checkpoints/wan
huggingface-cli download black-forest-labs/FLUX.2-dev --local-dir checkpoints/flux

# Once done, every future instance just attaches this volume — no re-download
```

The persistent volume is now your "configured environment." Costs ~$20/month for 200GB but saves hours of setup time per instance launch.

---

## LoRA training workflow

LoRAs are how you get channel-specific visual consistency. Without them, FLUX outputs drift across episodes and the channel looks inconsistent. With them, every chapter card, every owl mood board, every conceptual B-roll keyframe shares the same aesthetic.

### What to train LoRAs on

For your project, three useful LoRAs in priority order:

1. **Channel aesthetic LoRA** — trained on 20-40 hand-picked images representing the channel's editorial style (Wes Anderson + Hopper + Fantastic Mr. Fox + your specific palette). Applied at low weight (0.3-0.5) on every FLUX generation to keep visual consistency.

2. **Owl character LoRA** — trained on rendered owl screenshots (front, 3/4, side, in different poses). Lets FLUX generate the owl in new compositions without inconsistency. Useful for promo art, social posts, scenes you don't want to render in Blender.

3. **Map/cartographic style LoRA** — only if your map textures need a custom illustrative look beyond what Mapbox provides. Probably skip initially.

### LoRA training on Verda

Use the same instance pattern, longer-running:

```bash
# Terraform up a training box (H100 spot, ~$0.80/h, expect 8-15hr)
terraform apply -var="run_id=lora-channel-v3" -var-file="workloads/lora_train.tfvars"

# SSH in, install training tool (kohya-ss or ai-toolkit for FLUX)
ssh ubuntu@<ip>
cd /mnt/models
git clone https://github.com/ostris/ai-toolkit.git
cd ai-toolkit && pip install -r requirements.txt

# Place training images in /mnt/models/training_sets/channel_v3/
# Configure config/channel_v3.yaml (resolution, learning rate, steps, etc.)
# Start training in tmux
tmux new -s train
python run.py config/channel_v3.yaml
# Ctrl-b d to detach

# Come back hours later, check progress
tmux a -t train

# When done, the LoRA file is in /mnt/models/loras/ — already on the persistent volume
# Tear down the training instance
terraform destroy ...
```

Total cost for a single FLUX LoRA at 8-15hr on H100 spot: ~$6-12. Cheap relative to the visual leverage.

**Pro tip:** train on the dataset, evaluate by generating 10 test images with the LoRA, decide if it captures what you want, iterate if not. Don't train once and expect perfection. Plan for 2-3 training runs per LoRA.

### Where the LoRAs get used after training

Once a LoRA is on `/mnt/models/loras/`, it's available to every future ComfyUI instance. Reference it in workflow JSONs:

```json
{
  "lora_stack": [
    { "name": "channel_aesthetic_v3", "strength": 0.4 },
    { "name": "owl_character_v1", "strength": 0.7 }
  ]
}
```

This connects to the B-roll layer's `.meta.json` schema — the LoRA stack is recorded per generation for reproducibility.

---

## SSH + tmux discipline

When you SSH in, immediately `tmux new -s work` or `tmux attach -t work`. Reason: SSH connection dies (network drop, laptop sleep) → tmux session keeps running → job doesn't restart from zero.

Minimal `~/.ssh/config` on your laptop:

```
Host verda
  HostName <set-from-terraform-output>
  User ubuntu
  IdentityFile ~/.ssh/id_rsa
  ForwardAgent yes
  ServerAliveInterval 30
  ServerAliveCountMax 4
```

A small wrapper that pulls the IP from Terraform output:

```bash
#!/bin/bash
# infra/verda_ssh.sh
cd "$(dirname "$0")/../infra"
IP=$(terraform output -raw instance_ip)
ssh ubuntu@$IP
```

Once on the instance, standard pattern:
- Pane 1: the job running (training, batch generate)
- Pane 2: `nvtop` watching GPU utilization
- Pane 3: free for `tail -f` on logs

`Ctrl-b d` detaches. SSH out. Come back later, `ssh verda; tmux a -t work`.

---

## File sync

Three patterns:

**rsync over SSH (preferred for outputs):**
```bash
# pull all outputs from remote
rsync -avz ubuntu@verda:/home/ubuntu/outputs/ ./output/

# push code changes
rsync -avz ./broll/ ubuntu@verda:/home/ubuntu/GeoPoAI/broll/ \
  --exclude '__pycache__' --exclude '.git'
```

**Git for code (preferred for iteration):**
- Push changes locally → SSH in → `git pull`
- Cleaner version history than rsync
- Slightly slower for frequent small edits

**SSHFS** for "feels like local":
```bash
mkdir -p ~/mnt/verda
sshfs ubuntu@verda:/home/ubuntu ~/mnt/verda
# remote dir now appears at ~/mnt/verda locally
# fine for browsing, slow for large files
umount ~/mnt/verda
```

Skip cloud storage for transit — direct rsync is faster, simpler, and free.

---

## Cost budget (realistic for $300)

| Bucket | Amount | What it buys |
|---|---|---|
| AI video generation (~20 episodes) | $60 | ~2000 LTX clips + ~200 Wan clips, H100 spot |
| Presenter Cycles final renders | $40 | ~10 production presenter clips |
| LoRA training (channel + owl) | $25 | 2 LoRAs at 8-15hr each on H100 spot |
| Persistent volume (200GB, 4 months) | $80 | Always-present model storage |
| ComfyUI iteration / debugging | $20 | Interactive on-demand time |
| Image generation (FLUX) | $5 | Negligible — runs on instances already running |
| Buffer / dead ends | $70 | You will burn some money on mistakes |

The persistent volume is the biggest line item once you account for it — it costs every month whether you use it or not. ~$0.10/GB/month × 200GB = $20/month. Worth it because re-downloading 100GB of models on every fresh instance is hours of compute time you'd otherwise pay for.

Spot pricing on the compute buckets is the difference between this fitting and not fitting. Don't run batch jobs on-demand.

---

## Cost monitoring habits

**Daily during active development:** open the Verda dashboard, look at running instances. If you forgot to destroy one, kill it now.

**Weekly:** look at billing summary. Biggest line items tell you where to optimize.

**Hard budget alert** at $250 of your $300, kill-switch at $290. Even $20 over budget is a sign something's wrong.

**Tag your Terraform runs.** Use distinct `run_id` values per workload so the billing report breaks down by purpose.

---

## What runs where — the full split

```
Local (RTX 3070 Ti):
- Mapbox/Playwright pipeline (done)
- Manim renders at preview quality
- All Blender authoring + preview renders for the owl
- Stock B-roll fetching (cascade orchestrator)
- TTS generation (fishaudio/s2-pro runs locally)
- Schema validation, orchestration testing
- Final composition (ffmpeg)
- Claude Code iteration loops on 3D and code

Verda on-demand (short sessions, < 30min):
- ComfyUI debugging when something's broken
- One-off Wan 2.2 generation when LTX results need verification

Verda spot (batch jobs):
- AI B-roll batch generation (30-50 clips)
- Blender Cycles final renders for production presenter clips
- LoRA training (rare — when you decide to refresh aesthetic)
- FLUX batch image generation (chapter cards, mood boards)
```

You shouldn't need Verda day-to-day. You need Verda for batched heavy compute, then you tear down.

---

## The Claude Code 3D iteration loop — in detail

### The premise

Claude Code is a CLI agent that uses Claude under the hood. Claude is multimodal — it can read PNG images. So Claude Code can read a rendered preview image and describe what it sees.

The iteration loop:

```
1. You: "make the owl's brow tufts more asymmetric"
2. Claude Code: edits scripts/edit_owl_brow.py to do the change programmatically
3. Claude Code runs: blender --background characters/owl.blend \
                    --python scripts/edit_owl_brow.py
4. Script edits the .blend, saves, then renders preview PNGs to /tmp/
5. Claude Code reads /tmp/qc_grid.png and stdout stats
6. Claude Code: "I made the left brow flare 0.3 wider than the right.
                Want me to push it further?"
7. You also open /tmp/qc_grid.png locally, give feedback
8. Repeat
```

### What makes this fast

Three things to optimize.

**Preview render must be under 5 seconds.** That's the upper bound for "feels interactive." Means:
- Eevee, not Cycles
- Workbench shading mode for mesh-only work (no materials/lighting needed)
- 800x600 or smaller resolution
- 16 TAA samples max

**Multi-angle composited into one PNG.** Don't make Claude Code hunt across 4 separate files. The render script produces front + 3/4 + side + isometric, composites into a 2x2 grid in one PNG. One read, full picture.

**Stats dumped to stdout in a parseable format.** Vert count, face count, shape key list, bone hierarchy, recent errors. Claude Code reads stdout directly. For most edits, stats alone tell Claude Code whether the edit succeeded; the image confirms it looks right.

### The QC render script

`scripts/qc_render.py`:

```python
"""
QC render: produces a composited multi-angle preview of a Blender scene.
Designed for fast Claude Code iteration loops.
"""
import bpy
import os
from math import radians

OUT_DIR = "/tmp"
TARGET_OBJECT = "Owl_Mesh"
ANGLES = [
    ("front",   (0,    -3.5, 1.5), (radians(90), 0, 0)),
    ("3q",      (2.5,  -2.5, 1.5), (radians(90), 0, radians(45))),
    ("side",    (3.5,   0,   1.5), (radians(90), 0, radians(90))),
    ("iso",     (2.5,  -2.5, 2.5), (radians(60), 0, radians(45))),
]
RESOLUTION = (800, 600)
SAMPLES = 16

def setup_render():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'  # check your Blender version
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]
    scene.eevee.taa_render_samples = SAMPLES
    scene.render.image_settings.file_format = 'PNG'
    # for mesh-only iteration with no materials needed, even faster:
    # scene.render.engine = 'BLENDER_WORKBENCH'

def render_angle(name, position, rotation):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new(f"qc_cam_{name}")
    cam_obj = bpy.data.objects.new(f"qc_cam_{name}", cam_data)
    cam_obj.location = position
    cam_obj.rotation_euler = rotation
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    out_path = os.path.join(OUT_DIR, f"qc_{name}.png")
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    return out_path

def composite_grid(paths):
    """Composite 4 PNGs into a 2x2 grid using Pillow."""
    from PIL import Image
    imgs = [Image.open(p) for p in paths]
    w, h = imgs[0].size
    grid = Image.new('RGB', (w * 2, h * 2))
    grid.paste(imgs[0], (0, 0))
    grid.paste(imgs[1], (w, 0))
    grid.paste(imgs[2], (0, h))
    grid.paste(imgs[3], (w, h))
    out = os.path.join(OUT_DIR, "qc_grid.png")
    grid.save(out)
    return out

def dump_stats():
    obj = bpy.data.objects.get(TARGET_OBJECT)
    if not obj:
        print(f"STATS: object '{TARGET_OBJECT}' not found")
        return
    mesh = obj.data
    print(f"STATS_VERTS: {len(mesh.vertices)}")
    print(f"STATS_FACES: {len(mesh.polygons)}")
    if mesh.shape_keys:
        keys = [sk.name for sk in mesh.shape_keys.key_blocks]
        print(f"STATS_SHAPE_KEYS: {keys}")
    arm = bpy.data.objects.get("Owl_Armature")
    if arm:
        bones = [b.name for b in arm.data.bones]
        print(f"STATS_BONES: {bones}")
    mats = [m.name for m in mesh.materials if m]
    print(f"STATS_MATERIALS: {mats}")

def main():
    setup_render()
    paths = []
    for name, pos, rot in ANGLES:
        paths.append(render_angle(name, pos, rot))
    grid_path = composite_grid(paths)
    print(f"GRID: {grid_path}")
    dump_stats()

if __name__ == "__main__":
    main()
```

Claude Code invokes:
```bash
blender --background characters/owl.blend --python scripts/qc_render.py
# parses stdout for STATS_* lines
# reads /tmp/qc_grid.png as image input
```

Claude Code sees the 4-up grid image plus structured stats. It can comment on visual changes ("the brow asymmetry is now more pronounced on the left, ~30% wider") and confirm structural integrity ("vert count went from 8412 to 8419, +7 verts, expected for a small sculpting edit").

### For material/shader iteration

Workbench shading hides materials. When iterating on a material, use Eevee with minimal lighting:

```python
scene.render.engine = 'BLENDER_EEVEE_NEXT'
# add a 3-point light rig if scene doesn't have one
# or load a default HDRI for ambient
```

Material changes need lighting context, so this is slightly slower (5-10s per angle) but still iterative.

### For animation iteration

Render a flipbook — sample 6 frames evenly across the animation, composite into a 3x2 grid:

```python
TIMESTAMPS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]  # fractions of animation
for t in TIMESTAMPS:
    frame = int(scene.frame_start + t * (scene.frame_end - scene.frame_start))
    scene.frame_set(frame)
    render(...)
```

Claude Code sees the motion arc as still frames. Good enough for "does the gesture pose pass through expected key beats."

For actual motion review, render a small MP4 and watch it yourself. Stills work for Claude Code; motion needs your eyes.

### Where Claude Code falls short on 3D

Be realistic:

- **It can't rotate freely in 3D.** It sees fixed angles you chose.
- **Subtle proportions are hard to judge from screenshots.** Big structural changes come through. 2mm shifts don't.
- **Animation feel.** Stills don't capture timing.
- **Preview render is not final.** Workbench / preview Eevee misses material subtlety, SSS on feathers, accurate lighting.

Division of labor: Claude Code handles edits + structural verification. You handle the "does it feel right" judgment.

---

## When to use Verda for 3D, not just AI gen

Most 3D work is local. Two cases where Verda helps:

1. **Presenter final renders.** A 20-second presenter clip at full Cycles is 30+ minutes on your laptop. On a Verda B200 with frame parallelism, ~5 minutes wall-clock. Worth the $0.40-0.60.

2. **Heavy feather GeoNodes scenes.** If the .blend gets so heavy your laptop struggles to open it (viewport drops below 10 FPS even in proxy mode), render-farm it.

For these: rsync the .blend to the instance, run a remote Blender batch render, rsync results back, destroy instance. Same Terraform pattern.

---

## A typical work session, end-to-end

```
09:00  Pull latest from repo locally.
09:05  Open characters/owl.blend, work on a shape key.
09:30  Claude Code iteration loop on owl brow asymmetry, ~15 cycles.
       All local. Cost: $0.
10:30  Owl looks good. Commit.
10:35  Need to generate B-roll for ep017 — ~30 shots.
10:40  Write 30 shot specs in scripts/broll/ep017/.
10:45  cd infra && terraform apply -var="run_id=broll-ep017" \
       -var-file="workloads/comfyui.tfvars"
10:48  Instance ready (block volume already attached, ComfyUI started
       by bootstrap script). SSH in via wrapper script.
10:50  tmux a -t comfyui — ComfyUI already running. Submit batch via
       its API from a local script that drives it remotely.
10:55  Detach. Job runs unattended.
12:30  Job finishes. Local script auto-rsyncs outputs.
12:31  ./destroy_comfyui_instance.sh. Instance gone. Persistent volume stays.
       Total Verda spend for batch: ~$1.50 (1.8hr H100 spot at $0.80/h).
12:35  Review outputs locally, mark good/bad.
14:00  Decide 5 shots need re-prompting. Repeat the cycle for a small batch.
14:25  Done. Second batch cost: ~$0.40.
14:30  Manim renders for data viz beats. Local.
16:00  Final ffmpeg compose. Local.
17:00  Episode done. Total Verda spend today: ~$2.
```

Pattern: Verda runs are short, deliberate, batched. Most of the day is local + free.

---

## Failure modes to watch for

- **Forgot to destroy instance overnight.** $20-50 gone. Terraform makes this less likely (you have a `terraform destroy` muscle memory), but still set a daily check.
- **Spot evicted mid-batch.** Your batch script must checkpoint and resume. Test the resume path before depending on it.
- **Persistent volume growing unbounded.** Models accumulate. Periodically check `df -h /mnt/models` and prune unused checkpoints/LoRAs.
- **Terraform state file lost.** `infra/terraform.tfstate` tracks what's running. Lose it and you can't manage existing resources via Terraform. Commit it to git (it's not secret if you don't put credentials in it) or use a remote backend (S3, similar).
- **Bootstrap script broken.** If `comfyui_bootstrap.sh` fails partway, ComfyUI doesn't start. SSH in, check `/var/log/cloud-init-output.log` or wherever Verda logs startup script output. Fix the script, re-apply.
- **Persistent volume not attaching cleanly to new instance.** Race condition during boot. Sleep 5s before mount in bootstrap, or add a retry loop.

---

## Useful commands

```bash
# bring up the standard ComfyUI box
cd infra && terraform apply -var="run_id=$(date +%s)" \
  -var-file="workloads/comfyui.tfvars"

# tear it down
cd infra && ./destroy_comfyui_instance.sh <run_id> \
  -var-file="workloads/comfyui.tfvars"

# what's running
cd infra && terraform show | grep -A 3 "verda_instance"

# SSH wrapper (gets IP from terraform)
./infra/verda_ssh.sh

# panic button (kill everything in Terraform state)
cd infra && ./destroy_comfyui_instance.sh <run_id>   # never bare terraform destroy

# check current Verda balance via API
curl -H "Authorization: Bearer $TOKEN" https://api.verda.com/v1/balance

# how much have I spent this month
# (check via web dashboard — Billing page)
```

---

## Summary — simplified

1. **Configure once, snapshot the block volume, deploy many.** Persistent volume holds models; instances are ephemeral.
2. **Spot for batch, on-demand for interactive.** Spot is 25-65% cheaper depending on GPU; only available on Instances and Serverless Containers.
3. **Instance is always either actively running a job or destroyed.** No idle time.
4. **One ComfyUI instance hosts everything** — LTX, Wan, FLUX, your LoRAs. Don't separate them.
5. **Terraform for provisioning.** `terraform apply` brings the instance up; `./destroy_comfyui_instance.sh` tears down **only** the instance. Both in seconds.
6. **Skip managed endpoints.** Self-hosted gives you LoRAs and free image gen when an instance is already running.
7. **Your laptop handles all authoring; Verda handles batch heavy compute.**
8. **For 3D iteration with Claude Code:** fast preview render + multi-angle composite + stdout stats. The image and stats together tell Claude Code everything.
9. **Hard budget alerts. Tag job runs. Daily check.**

A few hundred dollars goes far when you're disciplined about idle time and use spot for batches. Most of your project work is free (local). Verda is for the moments when you need 32GB+ VRAM, and you pay only for those minutes.

---

## Session manager (`pipeline/gpu_session.py`)

One Python entry point replaces manual terraform ceremony: **up → health → use → auto-down**.
Generic across workloads (ComfyUI today; blender_render / lora_train; future TTS as config).

### Commands

```bash
# Prefix Python/tests with conda env; source Verda creds for terraform:
set -a && source /home/rawline/GeoPoAI/.env && set +a

conda run -n geopo python pipeline/gpu_session.py up comfyui_setup --verbose
conda run -n geopo python pipeline/gpu_session.py status comfyui_setup
conda run -n geopo python pipeline/gpu_session.py run comfyui -- python pipeline/broll.py shot.json
conda run -n geopo python pipeline/gpu_session.py watchdog comfyui
conda run -n geopo python pipeline/gpu_session.py down comfyui_setup
```

Workload registry: `infra/sessions.json`. Laptop session state: `infra/.session_state.json` (gitignored).

### Idle + budget insurance (two layers)

| Layer | Where | Behavior |
|-------|-------|----------|
| **Primary** | Laptop `watchdog` | Polls ComfyUI `/queue` + `/history`; SSH workloads use `last_activity_at` in session state. `idle_minutes` → `down`. `max_session_hours` → force `down` + loud log. |
| **Backstop** | VM cron (`lib_deadman.sh`) | `@reboot` sleep `max_session_hours + 30m`, then Verda API `delete` on **instance only** (no `volume_ids` — models volume survives). |

Forgot-the-H100-overnight: laptop watchdog is primary; VM cron fires even if the laptop sleeps.

### Models volume (never destroyed by session manager)

- Dashboard name: `geopoai-models-persistent`
- Volume ID (setup-001): `a4e5300f-32c3-41f4-9a74-d057fb7d628f`
- `gpu_session down` runs `terraform destroy -target=verda_instance.this` only — same guard as `destroy_comfyui_instance.sh`.

### Cost estimates

`status` prints `estimated_cost_usd` from `gpu_hourly_usd` in `sessions.json` — **estimates only**; check Verda Billing for truth.

### B-roll activity hook (future)

`from pipeline.gpu_session import record_activity` — call on each shot to refresh `last_activity_at` when not using ComfyUI `/history` idle detection. Not wired in `pipeline/broll.py` yet (W18 lane).

### Background watchdog

```bash
nohup conda run -n geopo python pipeline/gpu_session.py watchdog comfyui > /tmp/gpu-watchdog.log 2>&1 &
```

Or a systemd user timer on the laptop (document your unit locally).

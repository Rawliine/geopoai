# W19 — Infra: generic GPU session manager + idle/budget watchdogs

Branch: `agents/w19-infra` · Depends on: nothing (may run any time in Wave 1).
**Care: this lane spends real money when testing. Use the cheapest GPU tfvars
for live tests and ALWAYS destroy. Never touch the models volume resource.**

## Goal
Replace the manual terraform ceremony with one Python entry point usable by
humans and (later) the orchestrator: up → health → use → auto-down. Generic
across workloads — comfyui today; blender_render / lora_train tfvars already
exist; S2-pro TTS will join later as config, not code.

## Allowlist
pipeline/gpu_session.py (new) · infra/sessions.json (new registry) ·
infra/*.sh (edits allowed, deletions not) · infra/OPERATOR_RUNBOOK.md
(append a "session manager" section) · tests/test_gpu_session.py (new)

## Read first
infra/OPERATOR_RUNBOOK.md (whole file — phases, run_id conventions, the
prevent_destroy guard) · apply_comfyui_setup.sh · destroy_comfyui_instance.sh ·
wait_for_instance_ip.sh · compute.tf (lifecycle guard) · workloads/*.tfvars

## Checklist

### T1 — Workload registry
`infra/sessions.json`: workload name → { tfvars: [...], health:
{ type: "http", port: 8188, path: "/" } | { type: "ssh" }, env_export:
"BROLL_COMFYUI_URL" | null, default_gpu_profile, idle_minutes,
max_session_hours }. Entries: comfyui (production), comfyui_setup,
blender_render, lora_train.

### T2 — Session CLI
`python pipeline/gpu_session.py up|status|down|run <workload> [--run-id auto]`
- `up`: terraform apply with the workload's tfvars (run_id auto-generated
  `"<workload>-<date>-<n>"` unless given), wait for IP (reuse/port the logic
  of wait_for_instance_ip.sh), poll health endpoint until ready, update the
  exported env var in `.env` (sed in place, keep a `.env.bak`), tail
  bootstrap log on `--verbose`. Refuses `up` if a live session for the same
  workload exists (state file `infra/.session_state.json`).
- `down`: targets ONLY the instance resource — port
  destroy_comfyui_instance.sh's targeting; the models volume must be
  untouchable from this tool by construction (no code path may pass the
  volume resource to destroy).
- `run`: up if needed → execute a given shell command → schedule down per
  idle policy.
- `status`: instance state, IP, health, uptime, estimated session cost
  (GPU $/h table in sessions.json).

### T3 — Idle watchdog (laptop side)
`gpu_session.py watchdog <workload>`: daemonized loop (or systemd user
timer — implementer's choice, document) — if health endpoint has had no
activity for `idle_minutes` (ComfyUI: poll /history for queue activity;
fallback: file-touch protocol where pipeline/broll.py touches
`.session_state.json` on each shot — implement that touch), run `down`.
Hard cap: `max_session_hours` since up → force down + loud log.

### T4 — Dead-man backstop (VM side)
Append to the bootstrap (startup_scripts/): a cron entry on the VM that
self-terminates the instance via the Verda API after `max_session_hours`
(+30 min grace) regardless of laptop state — credentials via instance
metadata/env. This is the forgot-the-H100-overnight insurance. Document the
interaction in OPERATOR_RUNBOOK (laptop watchdog is primary; VM cron is
backstop).

### T5 — Tests + drill
test_gpu_session.py: registry parsing, state-file lifecycle, idle logic,
cost math (terraform calls mocked). Live drill (cheapest GPU profile):
up → health green → down; paste timeline in report; verify in Verda
dashboard the volume survived (volume ID in OPERATOR_RUNBOOK §3).

## Out of scope
New tfvars/GPU profiles · TTS workload implementation · orchestrator wiring ·
any change to verda_volume.models or its lifecycle guard.

## Acceptance
Live drill complete (up→down, volume intact); watchdog kills an idle test
session in a timed test; pytest green; runbook updated.

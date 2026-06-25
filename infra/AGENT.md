# AGENT.md — infra working rules

- **Start here:** `README.md` is the quick reference (credentials → first apply →
  SSH → destroy); `OPERATOR_RUNBOOK.md` is the narrative playbook + cost model
  (incl. the **"Session manager"** section for `pipeline/gpu_session.py`).
  Per-file Terraform map: `INFRA_FILE_REFERENCE.md`.
- **Prefer the session manager: `python pipeline/gpu_session.py up|status|down <workload>`.**
  It wraps apply/health/destroy, runs a best→worst GPU fallback, and keeps an
  idle/budget watchdog. Workloads live in `infra/sessions.json`.
- **Tear down with `gpu_session.py down <workload>` (or `./destroy_comfyui_instance.sh
  <run_id>`) — never bare `terraform destroy`.** Both destroy only the instance
  (`-target=verda_instance.this`); bare destroy tries to delete the persistent models
  volume (`prevent_destroy` blocks it, but don't rely on that). Add `--production` to
  the shell helper if the apply used `comfyui_production.tfvars`.
- **The models volume only dies via `gpu_session.py destroy volume`** (Verda API
  DELETE + `terraform state rm`, typed confirm) — never automatically, never from `down`.
- **Never commit secrets** (tfvars tokens, `terraform.tfstate` contents,
  `VERDA_CLIENT_ID` / `VERDA_CLIENT_SECRET`). `infra/.session_state.json` is gitignored.

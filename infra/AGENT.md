# AGENT.md — infra working rules

- **Start here:** `README.md` is the quick reference (credentials → first apply →
  SSH → destroy); `OPERATOR_RUNBOOK.md` is the narrative playbook + cost model.
  Per-file Terraform map: `INFRA_FILE_REFERENCE.md`.
- **Tear down with `./destroy_comfyui_instance.sh <run_id>` — never bare
  `terraform destroy`.** The helper destroys only the instance; bare destroy
  tries to delete the persistent models volume (`prevent_destroy` blocks it, but
  don't rely on that). Add `--production` if the apply used `comfyui_production.tfvars`.
- **Never commit secrets** (tfvars tokens, `terraform.tfstate` contents).

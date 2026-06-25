# W23 — Interactive GPU session wizard

Branch: `agents/w23-interactive-sessions` · Depends on: W19.

## Goal

Semi-automatic, operator-driven deploy: browse live Verda availability, pick GPU/region/spot in real time, optional model download, separate destroy instance vs destroy volume.

## Allowlist

`pipeline/gpu_session.py` · `infra/sessions.json` · `infra/OPERATOR_RUNBOOK.md` · `tests/test_gpu_session.py`

## Checklist

### T1 — Availability browser

`build_gpu_offerings`, `fetch_verda_volumes`, `read_volume_state`, `gpus --all-locations`.

### T2 — `interactive` wizard

`gpu_session interactive` — browse → billing → volume menu → deploy → download gate.

### T3 — Destroy commands

`destroy instance` (alias `down`), `destroy volume` (Verda API + state rm).

### T4 — `setup` shortcut

Conditional download on live instance.

### T5 — Registry + runbook

`storage` block in `sessions.json`; OPERATOR_RUNBOOK interactive section.

### T6 — Tests

pytest for offerings, destroy guards, download gate, TTY guard.

## Acceptance

`pytest tests/test_gpu_session.py` green; operator can run `interactive` and `gpus --all-locations` with valid `.env`.

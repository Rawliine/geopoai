# W24 — Brain layer: swappable authoring brains (halt / CLI agent / LLM API)

Branch: `agents/w24-brain-layer` · Depends on: nothing (independent — may run in
parallel with W25/W26/W27).

## Goal
A standalone, self-contained layer that turns one authoring request —
`(instruction, json_schema, context)` — into a **schema-valid artifact dict**,
via interchangeable **brains**. Orchestration (W20) imports this layer and never
cares which brain ran. Three brains ship:

- `halt` — today's operator-in-the-loop: write the instruction + schema to disk,
  signal `awaiting_brain`; the operator's Claude Code session authors the file;
  the runner validates on the next `next`.
- `cli_agent` — shell out to an LLM CLI (`claude -p …`, or `gemini …`), capture
  stdout, parse + validate JSON. Uses the operator's subscription (no API key).
- `api` — **fully built** programmatic brain on **LangGraph**: author → validate →
  repair loop, provider via SDK (Anthropic default; Gemini optional), key from `.env`.

Brain is chosen **once per episode** (W20 resolves `episode.json.brain`); this lane
only provides the layer + a `select_brain(name)` resolver.

## Allowlist
`brains/` (new package) · `tests/test_brains.py` (new) · `requirements.txt`
(append optional deps) · `.env.example` (append API-key vars)

## Read first
`pipeline/broll.py` (claude_cli verifier — mirror its `claude -p` subprocess +
JSON-capture discipline) · `.env.example` (BROLL_VERIFIER / ANTHROPIC_API_KEY
conventions) · `docs/contracts/*.schema.json` (artifacts brains must satisfy)

## Checklist

### T1 — Brain protocol + repair loop
`brains/base.py`: `class Brain(Protocol)` with
`author(instruction: str, schema: dict, context: dict) -> dict`. A shared
`validate_and_repair(brain, …, max_repairs=2)` helper: validate the returned dict
against `schema` (jsonschema); on failure, re-prompt the brain with the validator
error appended. `BrainResult` carries `{artifact, brain, attempts, awaiting}`.

### T2 — Halt brain
`brains/halt.py`: writes `instruction.md` + `schema.json` into the stage dir,
returns `awaiting=True` (no artifact). Preserves the current manual workflow.

### T3 — CLI-agent brain
`brains/cli_agent.py`: configurable command template
(`claude_cli` → `claude -p {prompt}`, `gemini_cli` → `gemini -p {prompt}`); writes
the prompt (instruction + schema + context) to a temp file, runs the CLI, extracts
the first JSON object from stdout, returns it. No API key — subscription auth.

### T4 — API brain (LangGraph, full)
`brains/api.py`: a LangGraph graph `author → validate → (repair | done)`. Provider
abstraction (`AnthropicProvider` default using the Messages API + the latest Claude
model; `GeminiProvider` optional). Keys from `.env`. Deterministic temperature
default; token + `$`-estimate captured on `BrainResult` for QC/cost.

### T5 — Selector + config
`brains/select.py`: `select_brain(name, cfg) -> Brain` for
`halt | claude-cli | gemini-cli | api`. Per-brain config (model, command, temp)
read from `config/brains.json` (new, with safe defaults). `brains/README.md`:
the protocol, the three brains, how to add a fourth — this layer's SKILL equivalent.

### T6 — Tests
Protocol conformance for all three; `validate_and_repair` happy + repair paths;
cli_agent with a mocked subprocess returning JSON; api with a mocked provider;
selector resolves every name; bad name raises.

## Out of scope
Orchestration stage wiring + prompt *content* (W20 owns instructions) · uploads ·
TTS · changing artifact schemas.

## Acceptance
Each brain authors a trivial schema-valid artifact (cli/api mocked); `select_brain`
resolves all four names; repair loop fixes one deliberately-invalid first attempt;
`pytest tests/test_brains.py` green.

# Brain layer (W24)

Standalone authoring layer: `(instruction, json_schema, context)` → a
**schema-valid artifact dict**, via interchangeable brains. Orchestration (W20)
imports this package and never cares which brain ran.

## Protocol

```python
from brains import validate_and_repair
from brains.select import select_brain

brain = select_brain("claude-cli")
result = validate_and_repair(
    brain,
    instruction="Author a trivial greeting artifact.",
    schema={"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}},
    context={"episode_id": "ep001"},
)
```

- `Brain.author(instruction, schema, context) -> dict` produces a candidate artifact.
- `validate_and_repair` validates against `schema` (jsonschema Draft 2020-12) and
  re-prompts with validator errors up to `max_repairs` (default 2).
- `BrainResult` carries `{artifact, brain, attempts, awaiting, tokens, cost_usd}`.

## Brains

| Name | Module | Auth | Behavior |
|------|--------|------|----------|
| `halt` | `brains/halt.py` | operator | Writes `instruction.md` + `schema.json` to `context["stage_dir"]`; returns `awaiting=True`. |
| `claude-cli` | `brains/cli_agent.py` | Claude Code subscription | `claude -p … --output-format json`; parses first JSON object from stdout. |
| `gemini-cli` | `brains/cli_agent.py` | Gemini CLI subscription | `gemini -p …`; same JSON capture discipline. |
| `api` | `brains/api.py` | API key (`.env`) | LangGraph `author → validate → repair`; Anthropic Messages API default, Gemini optional. |

Brain is chosen **once per episode** (`episode.json.brain` — W20). This lane ships
`select_brain(name)` and packaged defaults in `brains/brains.json`. Orchestration
may override via `config/brains.json` (same shape) when present.

## Configuration

Packaged defaults (`brains/brains.json`):

```json
{
  "api": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "temperature": 0,
    "max_repairs": 2
  }
}
```

Environment (`.env`):

- `ANTHROPIC_API_KEY` — required for `api` brain with Anthropic provider.
- `BRAIN_API_PROVIDER` — `anthropic` (default) or `gemini`.
- `BRAIN_API_MODEL`, `BRAIN_API_TEMPERATURE` — model + deterministic default.
- `GOOGLE_API_KEY` — optional Gemini api provider.

CLI brains need the `claude` / `gemini` binary on `PATH` (subscription login).

## Adding a fourth brain

1. Implement `Brain` in `brains/<name>.py` (`name` property + `author`).
2. Register the name in `brains/select.py` (`_KNOWN_BRAINS` + factory branch).
3. Add defaults to `brains/brains.json`.
4. Extend `tests/test_brains.py` with protocol conformance + any mocks.

Keep brains generic — no orchestration imports, no stage-specific prompt content.

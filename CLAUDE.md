# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository. This file
is a **router**: it points at each layer's own docs instead of duplicating them.
Keep it thin — when a layer changes, update that layer's docs, not this file.

## What this project is

GeoPoAI turns scene JSON into MP4 clips for short-form geopolitical /
game-theory video. Several renderers share one scene-JSON convention
(`duration`, `timeline`, action-based events); an LLM (Claude Code) authors the
JSON. The composition layer assembles rendered clips with captions and a sound
pass into finished episodes.

## Layers and where their docs live

| Layer | Path | Status | Docs |
|---|---|---|---|
| Map renderer | `map_renderer/` | live | `map_renderer/docs/` (SKILL, AGENT, recap) |
| Manim renderer | `manim_renderer/` | live | `manim_renderer/docs/` (SKILL, AGENT, recap, plan) |
| B-roll | `broll/` | live | `broll/` (AGENT, plan, recap) |
| Presenter renderer | `presenter_renderer/` | in progress | `presenter_renderer/` (AGENT, plan, recap, SKILL) |
| Infra (GPU sessions) | `infra/` + `pipeline/gpu_session.py` | live | `infra/README.md` + `infra/OPERATOR_RUNBOOK.md` (Session manager) + `infra/AGENT.md` |
| Composition | `composition/` | in progress — see `plans/W15`–`W17` | — |
| Orchestration | `orchestration/` | in progress — see `plans/W20` | — |

## Running renders

Every render goes through the unified dispatcher, which routes on the scene's
`"renderer"` field (`"mapbox"` default, or `"manim"`):

```bash
python pipeline/render.py scripts/map/MA_AG.json my_clip     # -> output/my_clip.mp4
python pipeline/render.py scripts/manim/hello.json hello     # -> output/manim/hello.mp4
```

The per-engine entry points still work directly (`pipeline/render_scene.py` for
Mapbox, `pipeline/render_manim.py` for Manim). Mapbox rendering needs a `.env`
at the repo root:

```
MAPBOX_TOKEN=pk.eyJ1...
```

Programmatic use:

```python
import asyncio
from pipeline.render import render
path = asyncio.run(render(scene_dict, "clip_name"))
```

## Map data

Country geometry auto-provisions on first use. To pre-download or inspect:

```bash
python config/prepare_maps.py --list-versions
python config/prepare_maps.py --from-manifest --version latest
```

The dataset registry is `map_renderer/data_prep/map_versions.json` (aliases in
`map_aliases.json`). Generated geometry lands in `data/maps/<version>/`
(gitignored); downloads cache to `data/.cache/`. Scene-authoring details live in
`map_renderer/docs/SKILL.md`.

## Validating and testing

```bash
python -m manim_renderer.schema.validator scripts/manim/hello.json
pytest                                          # full suite
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Project-wide rules (enforced; see `.cursor/rules/agent-discipline.mdc`)

- **No hardcoded visual constants.** Colors, fonts, glow, timing, and safe
  areas come from `config/design_tokens.json` — the frozen brand source of
  truth (established in W02). Never inline hex values or font names.
- **Assets only via the manifest.** New icons/fonts/SFX/models enter through
  `tools/prepare_assets.py` + `assets/manifest.json` (a committed lockfile;
  every entry carries a `license` field). Never download assets ad hoc (W02).
- **Frozen contracts.** `docs/contracts/*.schema.json` and
  `config/design_tokens.json` change only via the lead — never inside a lane.
- **Each layer documents its own surface.** New actions/effects/params/flags go
  in `<layer>/docs/fragments/<lane>.md`, merged into that layer's `SKILL.md` at
  integration — feature lanes never edit `SKILL.md` directly.

## The plans/ workflow

Pre-launch work is organized as lanes under `plans/` — one spec file per lane
(`plans/W*.md`), each its own git worktree + branch + PR-sized diff, with one
commit per checklist item. Each lane commit has three parts: (1) subject
`<type>(<scope>): <summary>` with no marker; (2) a per-file bullet body; (3)
the `(W<lane>.T<item>)` marker alone on the final line — see
`plans/AGENT_PROMPTS.md` for the full example. Start at `plans/PLAN.md` for
the wave and dependency order, and `plans/AGENT_PROMPTS.md` for the ready-to-
paste Cursor dispatch prompts. Superseded or historical docs live under
`docs/archive/`.

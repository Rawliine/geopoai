# GeoPoAI

Two-engine pipeline for short-form geopolitical / game-theory video clips. Both engines consume scene JSON and produce MP4.

- **Mapbox engine** (`pipeline/render_scene.py` → `map_renderer/runner.py`) — Mapbox GL JS in headless Chromium (Playwright). HTML/CSS/JS live under `map_renderer/web/`. Renders maps, country fills, borders, arrows, ripples.
- **Manim engine** (`pipeline/render_manim.py`) — Manim Community Edition. Renders payoff matrices, game trees, charts, system diagrams. Live: dispatcher, 10 components, 8 named layouts across both formats, 4 auto-cleanup mutations plus role/layout restaging, 3 callout styles (neon default), and a three-tier scene validator. See `manim_renderer/docs/` for the phase roadmap.

A unified dispatcher (`pipeline/render.py`) routes by the `"renderer"` field on each scene JSON.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

`.env` at project root (Mapbox only):
```
MAPBOX_TOKEN=pk.eyJ1...
```

## Render a scene

```bash
# unified dispatcher (reads "renderer" field)
python pipeline/render.py scripts/map/MA_AG.json my_clip          # → output/my_clip.mp4
python pipeline/render.py scripts/manim/hello.json hello          # → output/manim/hello.mp4

# Manim QA smoke test — exercises every component, effect, callout style, mutation
python pipeline/render.py scripts/manim/qa_mega_h.json qa_mega_h

# direct entries (also still work)
python pipeline/render_scene.py scripts/map/MA_AG.json my_clip
python pipeline/render_manim.py scripts/manim/hello.json hello
```

Programmatic usage:
```python
import asyncio
from pipeline.render import render
path = asyncio.run(render(scene_dict, "clip_name"))
```

## Mapbox engine

### Map data

Country geometry is downloaded on first use (auto-provisioned). To download manually:

```bash
python config/prepare_maps.py --list-versions          # see all available datasets
python config/prepare_maps.py --from-manifest --version latest
python config/prepare_maps.py --from-manifest --version 1991_ceasefire
```

Downloaded data goes to `data/maps/<version>/` (gitignored). Downloads are cached to `data/.cache/`.

**Available versions** (defined in `map_renderer/data_prep/map_versions.json`):

| Version | Resolution | Description |
|---|---|---|
| `latest` | 10m | Natural Earth countries — Morocco + W. Sahara merged |
| `1991_ceasefire` / `ceasefire` | 10m | Natural Earth map units — Morocco + W. Sahara split |
| `ne_10m_sovereignty` | 10m | Sovereignty units — sovereign states vs. territories |
| `ne_50m_countries` / `fast` | 50m | Lower resolution — faster for wide-angle scenes |
| `ne_110m_countries` / `global` | 110m | Minimal geometry — planetary overview shots |

To add a new dataset: add one entry to `map_renderer/data_prep/map_versions.json`. No code changes needed.

### Scene JSON shape

```json
{
  "renderer": "mapbox",
  "duration": 20,
  "_deterministic": true,
  "_fps": 60,
  "map_style": "dark",
  "camera": { "center": [-5.0, 30.0], "zoom": 3.0, "pitch": 25, "bearing": 0 },
  "timeline": [
    { "at": 0.0,  "action": "showLabel",   "params": { "id": "title", "text": "...", "position": { "x": 960, "y": 80 }, "effect": "label-slam" } },
    { "at": 1.5,  "action": "flyTo",       "params": { "center": [-8.0, 28.0], "zoom": 4.5, "duration": 1.5 } },
    { "at": 3.5,  "action": "applyBorder", "params": { "country": "Morocco", "version": "ceasefire", "effect": "border-trim" } },
    { "at": 8.0,  "action": "drawArrow",   "params": { "from": [-6.84, 33.97], "to": [-13.2, 27.15], "effect": "arrow-draw" } }
  ]
}
```

`renderer` defaults to `"mapbox"` if omitted. Coordinates are always `[longitude, latitude]`.

**Timeline actions:** `showLabel`, `removeLabel`, `applyFill`, `removeLayer`, `applyBorder`, `removeBorder`, `drawArrow`, `removeArrow`, `pulseRing`, `flyTo`, `cameraShake`, `clearOverlay` · **W11 territory:** `advanceFront`/`updateFront`/`removeFront`, `morphTerritory`, `maskImage` · **W12 flow/text:** `supplyLine`, `titleCard`, `statBox`, `showIcon` · **W13 camera/atmosphere:** `rotateAround`, `extrudeBars`, `showPlaceLabels`.

**Effects:** `fill-fade`, `fill-wipe`, `fill-ripple`, `fill-contested`, `hatch` · `border-trim`, `border-glow`, `border-marching`, `border-breathe`, `border-neon` (static) · `arrow-draw`, `arrow-travel`, `arrow-glow`, plus `drawArrow` styles `taper`/`arc` · `label-slam`, `label-typewriter`, `label-fade`.

**Scene keys (W13):** `format: "vertical"` (1080×1920), `idle_drift`, `atmosphere` (fog), `terrain`, `polish` (vignette/grain/haze). See `map_renderer/docs/SKILL.md` for the full authoring guide.

### Render modes

**Realtime** (default): records WebM via Playwright → converts to MP4. Fast.

**Deterministic** (`_deterministic: true`): one screenshot per frame via `stepTo(t)`. Consistent quality, slower. Use for final delivery.

## Manim engine

Live: dispatcher, 10 components, 8 layout solvers, 4 auto-cleanup mutations, 3 callout styles (neon default), validator overflow + composition-fit detection, and role-based composition + restaging. The full phase roadmap lives in `manim_renderer/docs/plan.md`.

JSON-authored Manim scenes for diagrams that don't sit on a map (payoff matrices, charts, system maps). The schema bans raw coordinates — composition uses named **layouts**, relative **anchors**, and **subject**-based callout placement. Every component has a **role** (`hero` / `primary` / `supporting` / `ambient` / `annotation` / `hidden`); the runner re-solves the layout on every composition change.

```bash
python pipeline/render.py scripts/manim/hello.json hello
# → output/manim/hello.mp4
```

### Scene JSON shape

```json
{
  "renderer": "manim",
  "format": "horizontal",          // "horizontal" (16:9) or "vertical" (9:16)
  "quality": "preview",             // "preview" | "draft" | "full"
  "scene": { "layout": "hero", "duration": 3, "theme": "dark" },
  "slots": {
    "main": { "at": 0.0, "action": "showTextCard",
              "params": { "id": "hello", "text": "GeoPoAI", "timing": "normal", "effect": "fade-in" } }
  },
  "overlays": [],
  "timeline": []
}
```

- **`slots`** — primary content, one per named slot defined by the chosen layout. The renderer positions the component at the slot's rect center.
- **`overlays`** — annotations/callouts (Phase 1: anchored to slot IDs).
- **`timeline`** — scene-level events that don't belong to a slot (camera moves, custom scenes).

**Available layouts:** `hero` (both formats), `split` (h) / `stacked` (v), `data-left` (h) / `data-top` (v), `trio` (h) / `trio-stack` (v), `title-body` (both).

**Available actions:** show* family (`showTextCard`, `showStatBlock`, `showMetricGroup`, `showCalloutBox`, `showBarChart`, `showLineChart`, `showTimeline`, `showGameTree`, `showAllianceWeb`, `showPayoffMatrix`); mutation/composition family (`removeComponent`, `highlightCell`, `crossOut`, `bestResponseArrow`, `setRole`, `setLayout`).

**Quality modes:** `preview` → 480p / 15fps · `draft` → 720p / 30fps · `full` → 1080p / 60fps. Vertical swaps width and height.

Every scene is validated before render. The validator runs three tiers (structural / per-action params / semantic) and rejects raw coordinate keys (`x`, `y`, `position`, …) anywhere in the JSON.

```bash
python -m manim_renderer.schema.validator scripts/manim/hello.json
```

### Engine layout

```
manim_renderer/
  scene.py          # JSONScene(MovingCameraScene) — the runner
  registry.py       # action name → component class
  theme/            # palette, typography, timing, easing (no raw values in components)
  layouts/          # named layouts per format (Phase 0: hero)
  components/       # base.py + one component per file
  effects/          # entrances/emphasis/exits/transitions (Phase 2)
  resolvers/        # anchor + size + camera (Phase 1)
  schema/           # scene_schema.json + per-action schemas + validator.py
  escape_hatch/     # hand-authored scenes for the 5% case (Phase 3+)
  tests/            # one test per component, plus golden frames + fuzz harness
```

See `manim_renderer/docs/` (`AGENT.md`, `SKILL.md`, `plan.md`, `recap.md`) for the full design, scene-authoring guide, and roadmap.

## Composition & orchestration (in progress)

These layers are being built — see [`plans/PLAN.md`](plans/PLAN.md) for scope, waves, and status.

- **Composition** (`composition/`) — assembles rendered clips into episodes: occupancy-aware caption burn-in, an automatic SFX/music sound pass, transitions, color grading, and multi-format export. Specs: `plans/W15`–`plans/W17`.
- **Orchestration** (`orchestration/`) — episode manifest plus a stage runner with hash-based selective re-render, QC gates, and publish, driven by Claude Code as the brain (no LLM API). Spec: `plans/W20`.

Brand consistency across every layer comes from `config/design_tokens.json` (palette, typography, glow, timing, safe areas) and the asset lockfile `assets/manifest.json` — both established in W02. Never hardcode visual constants or fetch assets ad hoc.

## Tests

```bash
pytest                                                # full suite
pytest tests/test_data_pipeline.py -v                 # Mapbox data prep
pytest manim_renderer/tests/components/ -v            # Manim components
```

## Config files (tracked by git)

| Path | Purpose |
|---|---|
| `map_renderer/data_prep/map_versions.json` | Mapbox dataset registry |
| `map_renderer/data_prep/map_aliases.json` | Short aliases (`ceasefire`, `fast`, …) |
| `config/prepare_maps.py` | Shim CLI → `map_renderer.data_prep.prepare_maps` |
| `manim_renderer/theme/palette.py` | Colors — must stay consistent with `map_renderer/web/css/*.css` (tokenized further in W02) |
| `manim_renderer/schema/scene_schema.json` | Top-level Manim scene contract |

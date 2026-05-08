# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

GeoPoAI is a geopolitical map animation pipeline. It renders scene JSON files into MP4 clips by headlessly driving a Mapbox GL JS page via Playwright, then encoding frames/video with ffmpeg.

## Running the renderer

Requires a `.env` file at the project root:
```
MAPBOX_TOKEN=pk.eyJ1...
```

Render a scene:
```bash
python pipeline/render_scene.py scripts/test_scene.json hook_clip
# → output/hook_clip.mp4
```

Programmatic usage:
```python
from pipeline.render_scene import render_scene
path = asyncio.run(render_scene(scene_dict, "clip_name"))
```

Data prep (run once per map version, or on-demand via auto-provisioning):
```bash
python data/prepare_ne_countries.py --from-manifest --version latest
python data/prepare_ne_countries.py --zip /path/to/ne_10m_admin_0_countries.zip --version latest
```

## Architecture

### Render pipeline flow

1. `pipeline/render_scene.py` — Python entry point. Resolves `country` shorthand in timeline entries to full GeoJSON via `data/maps/<version>/countries.featurecollection.geojson`, then launches Playwright.
2. Playwright opens `renderer/map.html` headlessly, injects the Mapbox token, waits for `window.sceneReady === true`, then calls either `window.playScene(scene)` (realtime) or `window.loadScene(scene)` + `window.stepTo(t)` per frame (deterministic).
3. `renderer/effects.js` — pure-JS animation engine. Implements `runTimeline`, `createDeterministicRuntime`, and all overlay effects (fills, arrows, labels, borders). No Mapbox dependency in this file.
4. `renderer/effects.css` — GPU-accelerated CSS animation classes applied by effects.js.
5. ffmpeg assembles the final MP4 from either a captured WebM (realtime) or a PNG frame sequence (deterministic).

### Two render modes

**Realtime** (default): Playwright records video as WebM while `playScene()` runs in real time → ffmpeg converts to MP4.

**Deterministic** (`_deterministic: true`): `loadScene()` sets up a frozen runtime, then `stepTo(t)` is called for each frame `t = i/fps`. One `page.screenshot()` per frame → ffmpeg assembles. Produces exactly `round(duration * fps)` frames. Use this for consistent motion quality and repeatable output with `_seed`.

### Scene JSON structure

Top-level scene keys:
- `duration` — total clip length in seconds
- `map_style` — `"dark"` | `"satellite"` | `"terrain"` | `"light"` | `"streets"` | raw Mapbox URL
- `camera` — opening camera: `{ center, zoom, pitch, bearing, duration }`
- `timeline` — array of `{ at, action, params }` entries
- `_deterministic`, `_fps`, `_seed`, `_nvenc_qp`, `_x264_crf` — render controls
- `_map_version` — default country data version (default: `"latest"`)
- `_include_islands` — whether to include island geometry (default: `false`)

### Country data versioning

`data/maps/` holds versioned country datasets. The version manifest is at `data/maps/versions.json`; aliases are at `data/maps/aliases.json` (e.g. `ceasefire → 1991_ceasefire`).

When a scene action uses `country: "Morocco"` without `geojson`, `render_scene.py` resolves it from `data/maps/<version>/countries.featurecollection.geojson`. If the version isn't cached locally, it auto-runs `data/prepare_ne_countries.py --from-manifest`.

Version resolution order per action: `params.version` → scene `_map_version` → `"latest"`.

### Overlay system

`renderer/map.html` has two overlay layers above the Mapbox WebGL canvas:
- `#arrows-layer` — SVG for arrows/paths
- `#labels-layer` — HTML divs for text labels

Both are reprojected on every camera `move`/`moveend` event via `MapEffects.bindReproject`. Geo-pinned elements carry `data-lng`/`data-lat` attributes; screen-fixed labels use `position: { x, y }`.

## Key files

| Path | Role |
|---|---|
| `pipeline/render_scene.py` | Main Python renderer, Playwright driver, country resolver |
| `renderer/map.html` | Mapbox GL JS page; exposes `window.playScene`, `window.loadScene`, `window.stepTo` |
| `renderer/effects.js` | JS animation engine: timeline sequencer, all effect implementations |
| `renderer/effects.css` | CSS animation classes (`fill-fade`, `border-marching`, `arrow-draw`, `label-slam`, etc.) |
| `data/prepare_ne_countries.py` | Downloads/processes Natural Earth shapefiles → versioned GeoJSON |
| `data/maps/versions.json` | Map version manifest with download sources |
| `data/maps/aliases.json` | Short alias → canonical version name |
| `scripts/` | Example scene JSON files |
| `tests/` | Browser-based HTML test pages for effects |

## Effects reference

**Fill effects**: `fill-fade`, `fill-wipe`, `fill-ripple`, `fill-contested`  
**Border effects**: `border-trim`, `border-glow`, `border-marching`, `border-breathe`  
**Arrow effects**: `arrow-draw`, `arrow-travel`, `arrow-glow`  
**Label effects**: `label-slam`, `label-typewriter`, `label-fade`

## Dependencies

Python: `playwright`, `python-dotenv`, `pyshp` (shapefile)  
System: `ffmpeg` (with optional `h264_nvenc` for GPU encoding), Chromium (installed via `playwright install chromium`)

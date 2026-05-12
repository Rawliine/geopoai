# GeoPoAI

Geopolitical map animation pipeline. Renders scene JSON files into MP4 clips by driving a headless Mapbox GL JS page via Playwright and encoding with ffmpeg.

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**2. Add your Mapbox token**
```
# .env
MAPBOX_TOKEN=pk.eyJ1...
```

## Render a scene

```bash
python pipeline/render_scene.py scripts/map/MA_AG.json my_clip
# → output/my_clip.mp4
```

Programmatic usage:
```python
import asyncio
from pipeline.render_scene import render_scene

path = asyncio.run(render_scene(scene_dict, "clip_name"))
```

## Map data

Country geometry is downloaded on first use (auto-provisioned). To download manually:

```bash
python config/prepare_maps.py --list-versions          # see all available datasets
python config/prepare_maps.py --from-manifest --version latest
python config/prepare_maps.py --from-manifest --version 1991_ceasefire
```

Downloaded data goes to `data/maps/<version>/` (gitignored). Downloads are cached to `data/.cache/`.

**Available versions** (defined in `config/map_versions.json`):

| Version | Resolution | Description |
|---|---|---|
| `latest` | 10m | Natural Earth countries — Morocco + W. Sahara merged |
| `1991_ceasefire` / `ceasefire` | 10m | Natural Earth map units — Morocco + W. Sahara split |
| `ne_10m_sovereignty` | 10m | Sovereignty units — sovereign states vs. territories |
| `ne_50m_countries` / `fast` | 50m | Lower resolution — faster for wide-angle scenes |
| `ne_110m_countries` / `global` | 110m | Minimal geometry — planetary overview shots |

To add a new dataset: add one entry to `config/map_versions.json`. No code changes needed.

## Scene JSON format

```json
{
  "duration": 20,
  "_deterministic": true,
  "_fps": 60,
  "map_style": "dark",
  "camera": { "center": [-5.0, 30.0], "zoom": 3.0, "pitch": 25, "bearing": 0 },
  "timeline": [
    { "at": 0.0,  "action": "showLabel",   "params": { "id": "title", "text": "...", "position": { "x": 960, "y": 80 }, "effect": "label-slam", "fontSize": "1.5rem", "color": "#f0c040" } },
    { "at": 1.5,  "action": "flyTo",       "params": { "center": [-8.0, 28.0], "zoom": 4.5, "pitch": 25, "duration": 1.5 } },
    { "at": 3.5,  "action": "applyBorder", "params": { "id": "ma-border", "country": "Morocco", "version": "ceasefire", "color": "#f1c40f", "width": 3, "effect": "border-trim", "duration": 1.2 } },
    { "at": 4.0,  "action": "applyFill",   "params": { "id": "ma-fill", "country": "Morocco", "color": "#f1c40f", "opacity": 0.35, "effect": "fill-fade", "duration": 1.0 } },
    { "at": 8.0,  "action": "drawArrow",   "params": { "id": "arrow1", "from": [-6.84, 33.97], "to": [-13.2, 27.15], "color": "#c0392b", "width": 2.5, "effect": "arrow-draw", "curved": true, "headed": true, "duration": 2.0 } },
    { "at": 11.0, "action": "removeArrow", "params": { "id": "arrow1" } },
    { "at": 12.0, "action": "pulseRing",   "params": { "id": "pulse1", "center": [-13.2, 27.15], "color": "#e67e22", "count": 3, "radius": 90, "duration": 4.0, "ringDuration": 1.8 } },
    { "at": 15.0, "action": "removeLabel", "params": { "id": "title" } }
  ]
}
```

**Coordinates are always `[longitude, latitude]`** — never `[lat, lng]`.

### Country shorthand

Use `country: "Name"` instead of inlining GeoJSON. Version can be overridden per action:

```json
{ "action": "applyFill", "params": { "country": "Western Sahara", "version": "ceasefire", ... } }
```

Version resolution order: `params.version` → scene `_map_version` → `"latest"`.

### Timeline actions

| Action | Purpose |
|---|---|
| `showLabel` | Text label (screen-fixed or geo-anchored) |
| `removeLabel` | Fade out a label |
| `applyFill` | Colored fill over a country/region |
| `removeLayer` | Fade out a fill |
| `applyBorder` | Animated border stroke |
| `removeBorder` | Fade/erase a border |
| `drawArrow` | Animated arrow between two geo points |
| `removeArrow` | Erase an arrow |
| `pulseRing` | Radar-style expanding rings from a geo point |
| `flyTo` | Camera move |
| `cameraShake` | Brief impact shake |
| `clearOverlay` | Remove all arrows and labels instantly |

### Effects

**Fill:** `fill-fade` · `fill-wipe` · `fill-wipe-rtl` · `fill-wipe-ttb` · `fill-wipe-btt` · `fill-ripple` · `fill-contested`  
**Border:** `border-trim` · `border-glow` · `border-marching` · `border-breathe`  
**Arrow:** `arrow-draw` · `arrow-travel` · `arrow-glow`  
**Label:** `label-slam` · `label-typewriter` · `label-fade`

See `map_animation_skill.md` for the full authoring guide.

## Render modes

**Realtime** (default): records WebM via Playwright → converts to MP4. Fast.

**Deterministic** (`_deterministic: true`): one screenshot per frame via `stepTo(t)`. Consistent quality, slower. Use for final delivery.

```json
{ "_deterministic": true, "_fps": 60, "_seed": 1, "_x264_crf": 14 }
```

## Config files (tracked by git)

| Path | Purpose |
|---|---|
| `config/map_versions.json` | Dataset registry — source URLs and metadata |
| `config/map_aliases.json` | Short aliases (`ceasefire`, `fast`, `global`, …) |
| `config/prepare_maps.py` | Download + process Natural Earth datasets |

## Tests

```bash
pytest tests/test_data_pipeline.py -v
```

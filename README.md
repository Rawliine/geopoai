# GeoPoAI

Put your token in `.env`:

`MAPBOX_TOKEN=...`

Run:

`python pipeline/render_scene.py scripts/test_scene.json hook_clip`

Deterministic render mode (recommended for consistent motion quality):

- Add these scene keys in your JSON:
  - `_deterministic: true`
  - `_fps: 60`
  - `_seed: 1`
  - `_nvenc_qp: 14` (for NVENC GPUs; lower is higher quality)
- Deterministic mode renders exactly `round(duration * fps)` frames and assembles with ffmpeg.
- Determinism validation:
  - Runtime target is logged as `round(duration * fps) / fps`.
  - Repeat runs with same scene + `_seed` should produce near-identical output.

Timeline actions currently supported:

- `showLabel`
- `drawArrow`
- `applyFill`
- `applyBorder`
- `removeBorder`
- `removeLabel`
- `removeLayer`
- `clearOverlay`
- `cameraShake`
- `flyTo`

Position formats:

- Geo-anchored: `[lng, lat]` (for camera, arrows, labels tied to map)
- Screen-fixed: `{ "x": number, "y": number }` (for labels only)

`applyBorder` params example:

```json
{
  "at": 1.2,
  "action": "applyBorder",
  "params": {
    "id": "dz-ma-border",
    "geojson": {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[-1.2, 34.7], [-2.5, 33.9], [-3.3, 32.7]]
      }
    },
    "color": "#f0c040",
    "width": 3,
    "effect": "border-marching",
    "duration": 1.2,
    "delay": 0
  }
}
```

Notes:

- Border effects come from `renderer/effects.css` (`border-trim`, `border-glow`, `border-marching`, `border-breathe`).
- In deterministic mode, `flyTo` timeline entries are handled by camera segment interpolation in `renderer/map.html`.

Simple country authoring (no giant inline geojson):

- For `applyFill` and `applyBorder`, you can provide:
  - `country` (e.g. `"Morocco"`, `"Algeria"`, `"Spain"`, `"France"`)
  - and omit `geojson`.
- At render time, `pipeline/render_scene.py` resolves `country` references into `geojson` features using:
  - `data/ne_10m_admin_0_countries.featurecollection.geojson`
- Backward compatible: if `geojson` is already present in the action params, it is used directly.

Example:

```json
{
  "at": 4.4,
  "action": "applyFill",
  "params": {
    "id": "algeria-fill",
    "country": "Algeria",
    "color": "#2ecc71",
    "opacity": 0.35,
    "effect": "fill-fade",
    "duration": 1.0
  }
}
```

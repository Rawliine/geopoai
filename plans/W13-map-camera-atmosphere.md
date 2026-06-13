# W13 — Map: camera language, atmosphere, vertical format, events/layout emission

Branch: `agents/w13-camera` · Depends on: W00 + W02.
**Start this lane first in Wave 1 — it owns core/runtime and the emitters.**

## Allowlist
map_renderer/runner.py · web/map.html · web/js/core/*.js ·
web/js/effects/camera.js · effects/atmosphere.js · web/css/base.css ·
web/css/atmosphere.css · scripts/map/qa_camera.json + qa_vertical.json (new) ·
map_renderer/docs/fragments/W13.md (new)

## Read first
runner.py (Playwright drive, viewport at ~1920x1080, realtime vs
deterministic paths) · web/js/core/runtime.js · map.html (sceneReady,
playScene/loadScene/stepTo) · docs/contracts/{events,layout}.schema.json ·
config/design_tokens.json (safe_areas)

## Checklist

### T1 — Camera easing language
- Easing presets for flyTo: `"swoop"` (fast depart, long decelerate —
  cinematic arrival), `"ramp"` (speed ramp: slow-fast-snap-slow), `"linear"`,
  `"gentle"`. Implement as custom `easing` functions passed to Mapbox flyTo
  (realtime) AND as the interpolator in deterministic camera stepping —
  both paths must match visually.
- New `rotateAround` action: `{ center, degrees, duration, easing }` —
  bearing orbit around a pinned point, pitch held.
- Scene-level `idle_drift`: `{ "enabled": true, "zoom_per_s": 0.004,
  "bearing_per_s": 0.1 }` — continuous subtle push-in/drift applied
  whenever no explicit camera action is active ("the map always breathes").
  Composes additively with flyTo (suspend during, resume after).
  Deterministic: drift derived from t.

### T2 — Atmosphere & polish layer
- Mapbox `setFog` on style load: atmosphere/horizon glow, token-tinted;
  scene key `atmosphere: { fog: true, stars: false }`.
- 3D terrain: scene key `terrain: { enabled: true, exaggeration: 1.4 }` →
  Mapbox DEM source + setTerrain. Works with pitch for the parallax/depth
  genre look.
- `extrudeBars` action (effects/atmosphere.js or camera.js — your call,
  document it): per-country extruded columns comparing a metric —
  `{ data: [{country, value}], max_height_m, role }` via Mapbox
  fill-extrusion on resolved country geometries.
- CSS overlay stack in map.html + atmosphere.css (above WebGL canvas, below
  labels): vignette (radial gradient, `grading.vignette_opacity` token),
  film grain (tileable SVG/PNG noise, `grain_opacity`, subtle 8-step
  positional loop driven by runtime t — deterministic), optional drifting
  haze layer (large soft gradient blobs, very slow t-driven pan). Scene key
  `polish: { vignette: true, grain: true, haze: false }` — defaults from
  tokens, all on a single `#polish-layer` div.

### T3 — Vertical format
Scene key `format: "vertical" | "horizontal"` (default horizontal):
- runner.py: viewport + record size 1080×1920 when vertical (parametrize
  the current hardcoded 1920×1080; also map.html's CSS dimensions — inject
  via the same mechanism the token CSS uses or set them from JS at load).
- Expose `window.sceneFormat`; label/callout/statBox/titleCard placement
  (labels.js reads it — coordinate via a `MapEffects.layoutHints` object you
  own in core: provides `safeRect()` from tokens safe_areas; W12's modules
  already call it if present — it ships in this lane, document it in
  core/utils.js).
- Screen-fixed positions in scene JSON become fraction-based when
  `{ "x": 0.5, "y": 0.1, "unit": "frac" }` (keep px for back-compat).

### T4 — Base-map label control
Default: on style load, hide all symbol layers (text + icons) from the
Mapbox base style. New action `showPlaceLabels`:
`{ "show": true, "types": ["country","city"], "within"?: bbox }` re-enables
selected base layers. Own overlay labels are unaffected.

### T5 — events.json emission (generic, all map actions)
In core/runtime.js: every executed action looks up `fn.eventMeta`
(fallback: type "label", intensity 0.4) and appends
`{t, type, phase:"start", intensity, role, id}`; camera actions emit
type "camera" with phase start/end pairs. runner.py pulls
`window.getEmittedEvents()` after render and writes
`output/<name>.events.json` (schema-valid).

### T6 — layout.json emission
core/reproject.js already touches every overlay element: on each reproject
(and at 2 Hz of runtime t), snapshot normalized bboxes of all overlay
elements (id, kind from a data-kind attribute — set data-kind in your core
element-creation helper; W11/W12 elements get it automatically if they use
the helper, else patch at snapshot time from class names).
runner.py writes `output/<name>.layout.json`.

### T7 — QA scenes
`qa_camera.json` (horizontal): swoop world→Maghreb, rotateAround Rabat,
idle drift visible during a 5s hold, terrain+fog on, vignette+grain on,
extrudeBars on 3 countries, base labels hidden, showPlaceLabels for cities
mid-scene. `qa_vertical.json`: same scene grammar framed for 9:16; labels
must respect caption band + platform margins (verify via layout.json).

### T8 — Docs fragment
`map_renderer/docs/fragments/W13.md`: easing presets, rotateAround,
idle_drift, atmosphere/terrain/polish scene keys, extrudeBars, vertical
format + frac positioning, showPlaceLabels, the events/layout sidecar files —
full params + one JSON example each, SKILL.md style.

## Out of scope
fills/borders/arrows/labels effect internals (only the shared hints/emitter
plumbing) · 3D models (W22) · captions/sound.

## Acceptance
Both QA scenes render in both modes (realtime + deterministic);
events.json + layout.json validate against schemas; vertical MP4 is
1080×1920; no layout.json box intersects the caption band in qa_vertical;
screenshots at 4 timestamps each in report.

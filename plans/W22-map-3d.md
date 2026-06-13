# W22 — Map: 3D models on the map (tanks, ships, missiles, resource icons)

Branch: `agents/w22-map3d` · Depends on: W13 (camera/runtime emission landed).
Heaviest map lane — last of the genre-grammar items.

## Allowlist
map_renderer/web/js/effects/models3d.js (stub exists since W00) ·
web/vendor/ (three.module.js pinned — ONLY addition) ·
tools/prepare_assets.py catalog entry + assets/manifest.json (models pack
entry only) · scripts/map/qa_models.json (new) ·
map_renderer/docs/fragments/W22.md (new)

## Read first
W00's models3d.js stub + registry pattern · effects/camera.js ·
core/runtime.js (deterministic stepping) · Mapbox GL JS custom layer
interface (CustomLayerInterface) docs · web/map.html (script order — three
must load before models3d.js; if a script tag is genuinely required, STOP
and report per discipline rule 2, the lead will add it).

## Checklist

### T1 — Model assets via the provisioner
Add a blessed `models-lowpoly` pack to assets/catalog.py: a CC0 low-poly
military/strategic glTF set (Quaternius or Kenney — verify CC0 at
implementation time, record license in manifest). Needed set: tank, ship,
jet, missile, soldier(s), oil barrel, wheat/crate, factory, radar. Keep the
extracted subset < 20 MB.

### T2 — Custom WebGL layer
models3d.js: one Mapbox CustomLayerInterface layer hosting a three.js scene
sharing the map's GL context; mercator-coordinate placement, soft shadow
blob (genre "lift" separation), tokens-driven rim/emissive tint by role.

### T3 — Actions
- `placeModel`: `{ id, model: "tank", at: [lng,lat], scale, heading, role,
  count?: n, spread_m? }` (count = small formation grid).
- `moveModel`: `{ id, to | along: [[lng,lat]...], duration, easing }` —
  heading follows path; deterministic-safe (t-driven, like W11/W12 motion).
- `removeModel` with exit (sink/fade).
- fn.eventMeta: type "model", intensity 0.7.

### T4 — Determinism + performance
Deterministic mode: model transforms derived purely from runtime t (verify
identical frames across two renders). Budget: ≤ 30 model instances, frame
time logged; if a deterministic 1080p frame exceeds ~200ms render budget on
this machine, reduce default shadow/material quality and note it.

### T5 — QA scene
qa_models.json: tank formation advancing along a path (with a W11
advanceFront underneath if merged — else alone), ships arcing a strait,
radar on a capital with pulseRing, camera swoop + rotateAround proving
models stay geo-anchored. Both formats.

### T6 — Docs fragment
`map_renderer/docs/fragments/W22.md`: placeModel/moveModel/removeModel
params + JSON examples, available model names, the instance budget.

## Out of scope
Terrain (done, W13) · extruded bars (done, W13) · animated skeletal meshes ·
particle weapons effects (backlog if ever).

## Acceptance
qa_models renders in realtime AND deterministic modes with identical-frames
check; models stay anchored through camera moves (screenshots during swoop);
events.json includes model events; license recorded in assets/manifest.json.

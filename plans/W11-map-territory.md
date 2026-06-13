# W11 — Map: territory effects (fills, invasion front, morph, hatch, masked images)

Branch: `agents/w11-territory` · Depends on: W00 + W02.

## Allowlist
map_renderer/web/js/effects/fills.js · effects/borders.js ·
web/css/fills.css · web/css/borders.css · scripts/map/qa_territory.json (new) ·
map_renderer/docs/fragments/W11.md (new)

(Vendored turf + flubber are already loaded by map.html — W00. Read core/
and registry.js but do not edit them.)

## Read first
web/js/core/{registry,runtime,reproject,utils}.js · effects/fills.js ·
docs/contracts/events.schema.json · config/design_tokens.json ·
map_renderer/docs/SKILL.md

## Checklist

### T1 — `border-neon` (static neon)
New effect in borders.css + borders.js: layered stroke — core stroke
`--glow-core-px` at `role.core`, halo via drop-shadow `--glow-halo-px` at
`role.glow`/`halo_opacity`. **No @keyframes** (entrance fade-in ≤0.4s
allowed, then fully static). Params: `{ country|geojson, role | color }`.
This becomes the default border look; border-glow stays as the "alert" variant.

### T2 — `advanceFront` action (invasion modeling) — the big one
Progressive territorial advance: a region of a country fills with color and
the colored zone grows along a front.
```jsonc
{ "action": "advanceFront", "params": {
    "id": "inv1", "country": "Ukraine",
    "from": [37.5, 47.9],            // origin point — OR "edge": "east"
    "progress": [ {"t": 0, "v": 0}, {"t": 4, "v": 0.45}, {"t": 7, "v": 0.6} ],
    "role": "threat",
    "front": { "softness_px": 14, "glow": true },   // soft animated edge
    "easing": "easeInOut"
} }
```
Implementation: clip the country polygon against an expanding mask —
growing geodesic circle around `from` (or sweeping half-plane for `edge`)
via turf intersect; re-compute the clipped SVG path on each runtime tick
(must work in BOTH realtime and deterministic `stepTo(t)` modes — drive from
runtime time, not wall clock). Front edge = stroked clip boundary with blur
(softness) + role glow. `v` = fraction of country area covered (calibrate
mask radius→area with turf.area, simple binary search is fine).
Also: `updateFront` (extend progress keyframes) and `removeFront`.

### T3 — `morphTerritory` action
Animate between two geometries (e.g. country across two map versions —
border change over time): flubber interpolation between the two outer rings
(largest-polygon heuristic for multipolygons; document the limitation).
Params: `{ id, country, version_from, version_to, duration, role }`.
The runner already resolves `country`+`version` to geojson — verify both
versions resolve (resolver auto-provisions).

### T4 — Pattern fills: hatching + gradient danger zones
`applyFill` gains `pattern: "hatch" | "gradient-radial" | "gradient-linear"`:
SVG `<defs>` patterns (45° hatch lines at role color over transparent;
gradients from `role.core` → transparent). Hatch = the "contested/occupied"
convention; combinable with fill-contested colors.

### T5 — `maskImage` action (flag/photo inside a country shape)
`{ id, country, image: "<path|url>", fit: "cover", opacity, pan: {…} }` —
SVG `<image>` clipped by the country path (clipPath), optional slow Ken
Burns pan (CSS transform, deterministic-safe via runtime-driven progress
like T2). Reprojection must keep image+clip in sync on camera moves (test
with a flyTo).

### T6 — Event metadata
Register event descriptors for every action this lane owns (consumed by
W13's generic emitter): advanceFront → type "fill" intensity 0.9;
border-neon → "border" 0.5; morphTerritory → "fill" 0.7; maskImage →
"image" 0.6. Mechanism: attach `fn.eventMeta = { type, intensity }` to each
registered action function (do NOT modify registry.js — it is W13/core
territory); W13's generic emitter reads `eventMeta` off the registry entries.

### T7 — QA scene
`scripts/map/qa_territory.json`: border-neon on Morocco; advanceFront with
3 keyframes; morphTerritory latest↔ceasefire on Morocco; hatch fill on
W. Sahara; maskImage flag inside Algeria; one flyTo mid-scene to prove
reprojection. Deterministic, 25s.

### T8 — Docs fragment
`map_renderer/docs/fragments/W11.md`: border-neon, advanceFront,
updateFront/removeFront, morphTerritory, pattern fills, maskImage — full
params + one JSON example each, SKILL.md style.

## Out of scope
Arrows/labels/icons (W12) · camera/atmosphere/vertical/emission (W13) ·
core/*.js · map.html.

## Acceptance
`python pipeline/render.py scripts/map/qa_territory.json qa_territory`
renders deterministically; frame screenshots at t=2/6/12/20 attached in
report; advanceFront area at v=0.5 visually ≈ half the country; no console
errors in the Playwright log.

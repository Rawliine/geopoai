# SKILL.md — Authoring Map Scene JSON

This file teaches an LLM how to write scene JSON files for the GeoPoAI map renderer.
Tone: be precise, use the exact key names, default to safe choices. The action and
effect tables below are verified against `map_renderer/web/js/effects/*.js` and
`map_renderer/web/css/*.css`.

---

## What the renderer does

The renderer reads a **scene JSON file**, drives a headless Mapbox GL JS browser page
via Playwright, and produces an MP4. A scene is a sequence of timed actions that add
fills, borders, arrows, labels, and pulse effects to a map.

The entry point is the unified dispatcher `pipeline/render.py` (or `pipeline/render_scene.py`
directly); the Mapbox implementation lives in `map_renderer/runner.py`. It resolves
`country:` shorthands to GeoJSON, then passes the full scene to the browser. All visual
logic lives in `map_renderer/web/js/` modules and `map_renderer/web/css/*.css`.

---

## Top-level scene structure

```json
{
  "duration": 20,           // total clip length in seconds (required)
  "map_style": "dark",      // "dark" | "satellite" | "terrain" | "light" | "streets" | raw Mapbox URL
  "camera": {               // opening camera — applied before timeline starts
    "center": [lng, lat],   // NOTE: longitude FIRST, then latitude
    "zoom": 4.5,
    "pitch": 25,            // 0 = top-down, 60 = dramatic tilt
    "bearing": 0,           // 0 = north up
    "duration": 1.0         // seconds for the initial ease-in (0 = instant)
  },
  "timeline": [ ... ],      // array of timed actions — see below
  "_deterministic": true,   // true = PNG frame sequence (consistent, slower render)
                            // false/omitted = realtime WebM (faster render)
  "_fps": 60,               // frames per second (only used in deterministic mode)
  "_seed": 1,               // random seed for camera shake
  "_nvenc_qp": 14,          // GPU encode quality (lower = better, 0–51)
  "_x264_crf": 14,          // CPU encode quality (lower = better, 0–51)
  "_map_version": "latest", // default country data version for all actions
  "_include_islands": false // include island geometry in country shapes
}
```

---

## Timeline actions

Every action follows this envelope:

```json
{ "at": 5.2, "action": "actionName", "params": { ... } }
```

`at` is seconds from scene start. Actions fire once. They are NOT loops.

---

### `applyFill` — colored fill over a country/region

```json
{
  "at": 3.0,
  "action": "applyFill",
  "params": {
    "id": "morocco-fill",       // unique id — required, used to remove later
    "country": "Morocco",       // resolves to GeoJSON via country data
    "version": "ceasefire",     // optional version override (see Country Resolution)
    "color": "#f1c40f",         // fill color (hex)
    "opacity": 0.35,            // fill opacity 0–1 (default 0.6)
    "effect": "fill-fade",      // see Effects Gallery below
    "duration": 1.0,            // animation duration in seconds
    "delay": 0,                 // seconds before animation starts
    "colorB": "#e74c3c",        // second color — only for fill-contested
    "origin": [lng, lat]        // ripple origin point — only for fill-ripple
  }
}
```

To remove a fill, use `removeLayer` (see below).

---

### `applyBorder` — animated border stroke

```json
{
  "at": 4.4,
  "action": "applyBorder",
  "params": {
    "id": "morocco-border",
    "country": "Morocco",
    "version": "ceasefire",
    "color": "#f1c40f",
    "width": 3,                 // stroke width in px (default 2.5)
    "effect": "border-trim",    // see Effects Gallery
    "duration": 1.2,
    "delay": 0,
    "glowColor": "#ff6b35"      // optional: glow color for border-glow
  }
}
```

---

### `removeBorder` — remove a border with exit animation

```json
{
  "at": 9.4,
  "action": "removeBorder",
  "params": {
    "id": "morocco-border",
    "exitDuration": 0.6         // optional, default 0.6s fade-out
  }
}
```

Schedule downstream actions ≥ 0.6s after `removeBorder` to avoid visual overlap.

---

### `drawArrow` — animated arrow between two geo points

```json
{
  "at": 11.0,
  "action": "drawArrow",
  "params": {
    "id": "advance-arrow",
    "from": [-6.84, 33.97],     // [lng, lat] origin
    "to": [-13.2, 27.15],       // [lng, lat] destination
    "color": "#c0392b",
    "width": 2.5,               // stroke width in px (default 2.5; keep ≤ 3 for clean look)
    "effect": "arrow-travel",   // see Effects Gallery
    "curved": true,             // bezier curve (default true)
    "arc": 110,                 // curve bow height in px (default 80)
    "headed": true,             // show arrowhead at destination (default true)
    "glowColor": "#ff4444",     // for arrow-glow — override glow color
    "duration": 3.5,            // total duration in seconds
    "delay": 0
  }
}
```

**`headed` behavior by effect:**
- `arrow-draw` + `headed: true` — arrowhead is deferred until the stroke finishes drawing. Correct and recommended for military advance / movement arrows.
- `arrow-travel` + `headed: true` — arrowhead sits at destination while the dot is still traveling. Usually wrong. Use `"headed": false` for travel arrows.
- `arrow-glow` + `headed: true` — arrowhead appears immediately with the path. Fine.

All arrow types draw on from origin→destination on appearance, and erase origin→destination on removal. Budget ~0.25–0.35× `duration` for the entrance draw-on.

---

### `removeArrow` — remove an arrow with exit animation

```json
{
  "at": 19.0,
  "action": "removeArrow",
  "params": {
    "id": "advance-arrow",
    "exitDuration": 0.6         // optional, default 0.6s erase from origin→destination
  }
}
```

---

### `removeLayer` — remove a fill (applyFill layer) with fade-out

```json
{
  "at": 15.0,
  "action": "removeLayer",
  "params": {
    "id": "morocco-fill",       // must match the id used in applyFill
    "exitDuration": 0.6         // optional, default 0.6s opacity fade
  }
}
```

---

### `pulseRing` — radar-style expanding rings from a geo point

```json
{
  "at": 19.0,
  "action": "pulseRing",
  "params": {
    "id": "pulse-city",
    "center": [-13.2, 27.15],   // [lng, lat]
    "color": "#e67e22",
    "count": 3,                 // number of rings (default 3)
    "radius": 90,               // max ring radius in px (default 80)
    "width": 2.5,               // ring stroke width (default 2)
    "duration": 4.0,            // total effect lifetime in seconds (default 4.0)
    "ringDuration": 1.8,        // per-ring expansion time in seconds (default 1.8)
    "delay": 0,
    "dotRadius": 5,             // static center dot radius (default 5; set 0 to hide)
    "dotColor": "#e67e22"       // dot color (default: matches color)
  }
}
```

`duration` is the **total lifetime** of the effect. Rings auto-space across it like
a radar. With `count: 3, duration: 4.0`, rings emit ~every 1.33s.

pulseRing removes itself automatically — no `removeLayer` needed.

---

### `showLabel` — text label (geo-pinned or screen-fixed)

```json
{
  "at": 0.0,
  "action": "showLabel",
  "params": {
    "id": "title-label",
    "text": "WESTERN SAHARA",
    "position": [-13.0, 24.5],  // [lng, lat] = geo-pinned, moves with camera
    "effect": "label-slam",
    "color": "#f0c040",
    "fontSize": "1.4rem",
    "duration": 0.4,
    "delay": 0,
    "charInterval": 70          // ms per character — for label-typewriter only
  }
}
```

Screen-fixed position (doesn't move with camera):
```json
"position": { "x": 960, "y": 60 }
```

> **Don't cover an effect with its own label.** A geo-pinned `showLabel` placed at
> (or very near) the same `[lng, lat]` as a `pulseRing` center, arrow endpoint, or
> icon renders on top of that effect and hides it. When labeling a point effect,
> either use a screen-fixed banner (`position: { x, y }`) or offset the label's
> `[lng, lat]` clear of the effect's radius.

Counter label:
```json
{
  "action": "showLabel",
  "params": {
    "id": "counter",
    "text": "",
    "position": { "x": 960, "y": 200 },
    "isCounter": true,
    "counterFrom": 0,
    "counterTo": 250,
    "counterSuffix": "K",
    "duration": 2.0,
    "effect": "label-fade"
  }
}
```

---

### `removeLabel` — fade out a label

```json
{ "at": 3.2, "action": "removeLabel", "params": { "id": "title-label" } }
```

---

### `flyTo` — camera move during the scene

```json
{
  "at": 2.3,
  "action": "flyTo",
  "params": {
    "center": [-2.49, 31.77],
    "zoom": 2.5,
    "pitch": 30,
    "bearing": 0,
    "duration": 1.2             // flyTo animation duration in seconds
  }
}
```

---

### `cameraShake` — brief shake for impact

```json
{
  "at": 8.0,
  "action": "cameraShake",
  "params": {
    "intensity": "medium",      // "light" | "medium" | "heavy"
    "durationMs": 400           // shake duration in milliseconds
  }
}
```

---

### `clearOverlay` — remove all arrows and labels instantly

```json
{ "at": 15.0, "action": "clearOverlay", "params": {} }
```

Use sparingly — no exit animation.

---

## Effects Gallery

### Fill effects (used in `applyFill`)

| Effect | What it does | Typical `duration` |
|---|---|---|
| `fill-fade` | Opacity 0→target. Universal, clean. | 0.8–1.5s |
| `fill-wipe` | Clip-path sweeps left→right revealing fill. | 1.2–2.0s |
| `fill-wipe-rtl` | Same, right→left. | 1.2–2.0s |
| `fill-wipe-ttb` | Top→bottom. | 1.2–2.0s |
| `fill-wipe-btt` | Bottom→top. | 1.2–2.0s |
| `fill-ripple` | Elastic scale 0→1 from `origin` point. | 0.8–1.4s |
| `fill-contested` | Alternates between `color` and `colorB` at set cadence. **`duration` = flash period** (not total lifetime). | 0.2–0.8s |
| `fill-contested-smooth` | Smooth crossfade between two colors (infinite). | 1.0–3.0s |

**fill-contested gotcha:** `"duration": 0.2` means a flash every 0.2 seconds —
rapid strobe effect. For a gentle dispute indicator use 0.5–0.8s. You must provide
`colorB` or the second color defaults to blue.

---

### Border effects (used in `applyBorder`)

| Effect | What it does | Typical `duration` |
|---|---|---|
| `border-trim` | Stroke draws itself on from start to end. | 1.0–2.5s |
| `border-trim-erase` | Reverse — stroke erases itself. | 1.0–1.5s |
| `border-glow` | Pulsing neon drop-shadow (infinite). | 1.5–3.0s |
| `border-marching` | Animated dashes — "marching ants" (infinite). | 0.6–1.2s (scroll speed) |
| `border-marching-reverse` | Same, reversed direction. | 0.6–1.2s |
| `border-breathe` | Opacity + stroke-width pulse (infinite). | 1.5–3.0s |

All borders fade out gracefully when removed with `removeBorder`.

---

### Arrow effects (used in `drawArrow`)

| Effect | What it does | Typical `duration` |
|---|---|---|
| `arrow-draw` | Path strokes itself on from origin to destination. | 1.5–2.5s |
| `arrow-travel` | A glowing dot travels along the path. **Use `duration ≥ 3.0s`** — shorter feels rushed. | 3.0–5.0s |
| `arrow-glow` | Static path with pulsing neon glow. | 2.0–3.0s |

All arrows draw on from origin→destination on appearance, and erase origin→destination
on removal.

---

### Label effects (used in `showLabel`)

| Effect | What it does | Typical `duration` |
|---|---|---|
| `label-slam` | Scale 1.3→1 with opacity snap. Impactful. | 0.3–0.6s |
| `label-typewriter` | Character-by-character reveal. Use `charInterval` (ms/char). | n/a — driven by charInterval |
| `label-fade` | Clean opacity fade-in with subtle upward drift. | 0.6–1.2s |

---

## Country resolution

Instead of providing raw GeoJSON, use the `country` shorthand:

```json
"country": "Morocco",
"version": "ceasefire"    // optional version; default = scene's _map_version or "latest"
```

Available versions are listed in `map_renderer/data_prep/map_versions.json`.
Aliases (like `"ceasefire"` → `"1991_ceasefire"`) are in `map_renderer/data_prep/map_aliases.json`.

When to use raw `geojson` instead:
- Custom regions not matching any country
- Precise sub-country boundaries
- Combining multiple countries into one fill

---

## Geo coordinates — critical rule

**Coordinates are always `[longitude, latitude]` — NOT `[lat, lng]`.**

- Morocco capital: `[-6.84, 33.97]` ✓ (lng=-6.84, lat=33.97)
- Common mistake: `[33.97, -6.84]` ✗ — renders in the middle of the ocean

Use Mapbox-style decimal degrees. No DMS notation.

---

## Timing best practices

1. **Leave breathing room.** Add ≥0.5s between label transitions, ≥1.5s after flyTo before adding new effects (flyTo is still animating).

2. **Exit buffer.** All removals (removeArrow, removeBorder, removeLayer) have a ~0.6s
   exit animation. Schedule the next action ≥0.6s after any removal to avoid overlap:
   ```
   { "at": 9.4, "action": "removeBorder", "params": { "id": "..." } }
   { "at": 10.0, "action": "applyBorder", ... }   ← 0.6s gap is enough
   ```

3. **arrow-travel speed.** Use `duration ≥ 3.0s`. At 2.0s the dot looks rushed.

4. **fill-contested duration = cadence.** 0.2s = strobe (use for "active conflict").
   0.5–0.8s = readable alternation (use for "disputed territory").

5. **pulseRing lifetime.** With `count: 3, duration: 4.0, ringDuration: 1.8`,
   rings emit at t≈0.67s, t≈2.0s, t≈3.33s — natural radar cadence.
   Don't use `duration < 2.5s` with `count: 3` or rings will overlap.

6. **Deterministic vs realtime.** Use `_deterministic: true` for final renders
   (consistent quality, slow). Omit or set `false` for drafts (fast, may have
   frame-rate variation). `pulseRing` rings are JS-driven in deterministic mode
   (scene-time accurate regardless of render speed). Infinite CSS effects
   (`border-glow`, `border-marching`, etc.) run correctly in both modes.

7. **Total duration.** Set `duration` (top-level) at least 0.5s beyond the last
   action's `at` + its animation duration. The clip cuts abruptly at `duration`.

8. **Label ≠ effect coordinate.** Never place a geo-pinned `showLabel` at the same
   `[lng, lat]` as a `pulseRing`, arrow endpoint, or icon — the label covers the
   effect. Label point effects with a screen-fixed banner (`position: { x, y }`) or
   offset the label clear of the effect's radius.

---

## Deterministic vs realtime

**Realtime** (`_deterministic: false` / omitted):
- Playwright records the browser as WebM; ffmpeg converts to MP4.
- Fast to render. May have slight frame variation.
- CSS animations run normally. All setTimeout/rAF effects work.

**Deterministic** (`_deterministic: true`):
- Playwright takes one screenshot per frame (`1/fps` seconds apart).
- JS calls `stepTo(t)` for each frame — CSS animations don't auto-advance.
- All effects have deterministic equivalents driven by `stepTo`.
- Use for final delivery. Slower render (one screenshot per frame × fps × duration).
- `_fps: 60` + `duration: 20` = 1200 screenshots.

---

## Worked example — 30-second scene

```json
{
  "duration": 30,
  "_deterministic": true,
  "_fps": 60,
  "map_style": "dark",
  "camera": { "center": [-2.49, 31.77], "zoom": 1.0, "pitch": 20, "bearing": 0, "duration": 0.5 },
  "timeline": [
    {
      "at": 0.0, "action": "showLabel",
      "params": { "id": "intro", "text": "THE WESTERN SAHARA CONFLICT",
        "position": { "x": 960, "y": 80 }, "effect": "label-slam", "fontSize": "1.6rem",
        "color": "#f0c040", "duration": 0.5 }
    },
    {
      "at": 1.5, "action": "flyTo",
      "params": { "center": [-10.0, 24.0], "zoom": 4.5, "pitch": 25, "bearing": 0, "duration": 2.0 }
    },
    {
      "at": 4.0, "action": "applyBorder",
      "params": { "id": "sahara-border", "country": "Western Sahara", "version": "ceasefire",
        "color": "#e67e22", "width": 3, "effect": "border-trim", "duration": 1.5 }
    },
    {
      "at": 5.5, "action": "applyFill",
      "params": { "id": "sahara-fill", "country": "Western Sahara", "version": "ceasefire",
        "color": "#e67e22", "opacity": 0.3, "effect": "fill-wipe", "duration": 1.2 }
    },
    {
      "at": 8.0, "action": "drawArrow",
      "params": { "id": "invasion", "from": [-6.84, 33.97], "to": [-13.2, 27.15],
        "color": "#c0392b", "width": 2.5, "effect": "arrow-draw",
        "curved": true, "arc": 110, "headed": true, "duration": 2.0, "delay": 0 }
    },
    {
      "at": 12.0, "action": "pulseRing",
      "params": { "id": "pulse1", "center": [-13.2, 27.15],
        "color": "#e67e22", "count": 3, "radius": 90, "duration": 4.0, "ringDuration": 1.8 }
    },
    {
      "at": 12.0, "action": "removeArrow", "params": { "id": "invasion" }
    },
    {
      "at": 17.0, "action": "removeLayer", "params": { "id": "sahara-fill" }
    },
    {
      "at": 17.0, "action": "applyFill",
      "params": { "id": "sahara-contested", "country": "Western Sahara", "version": "ceasefire",
        "color": "#e67e22", "colorB": "#2ecc71", "opacity": 0.35,
        "effect": "fill-contested", "duration": 0.5 }
    },
    {
      "at": 22.0, "action": "removeLabel", "params": { "id": "intro" }
    },
    {
      "at": 22.5, "action": "removeBorder", "params": { "id": "sahara-border" }
    },
    {
      "at": 28.0, "action": "flyTo",
      "params": { "center": [-2.49, 31.77], "zoom": 1.5, "pitch": 0, "bearing": 0, "duration": 2.5 }
    }
  ]
}
```

---

## Common mistakes

| Mistake | Fix |
|---|---|
| Forgetting `id` on fill/border/arrow | Always set `id` — you need it to remove the element later |
| `[lat, lng]` coordinate order | Always `[lng, lat]` — longitude first |
| Reusing the same `id` for two `applyFill` calls | Each fill needs a unique id; reuse updates the GeoJSON but keeps the same layer |
| `arrow-travel` with `headed: true` | The arrowhead sits at the destination while the dot travels — use `headed: false` |
| `fill-contested` `duration` too small (e.g. 0.01) | 0.2s = fast strobe; 0.5s = normal; 0.01s looks like one color |
| `pulseRing` removed before rings finish | Don't add a `removeLayer` for pulseRing — it self-destructs after `duration + ringDuration` |
| `removeLayer` id mismatch | The id must match the `id` used in `applyFill`, not the country name |
| Actions spilling past scene `duration` | Extend `duration` or trim the timeline — the MP4 hard-cuts at `duration` |
| `fill-contested` without `colorB` | Second color defaults to `#3498db` (blue) — always provide `colorB` |
| Very short `flyTo` before heavy effects | Give the camera at least 1.5s to settle before adding fills/borders |

---

# Wave-1 additions (W11–W14)

_Authored by lanes W11–W14 and integrated here as the authoring reference for their actions._


## W11 — Territory effects fragment

> Merged into `map_renderer/docs/SKILL.md` at integration. Documents border-neon,
> invasion-front modeling, territory morph, pattern fills, and masked images.

---

### `border-neon` effect (via `applyBorder`)

Static layered neon stroke — the default border look. `border-glow` remains the
pulsing alert variant.

```json
{
  "at": 0.5,
  "action": "applyBorder",
  "params": {
    "id": "morocco-neon",
    "country": "Morocco",
    "role": "highlight",
    "effect": "border-neon",
    "fadeIn": 0.35
  }
}
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `country` / `geojson` | string / object | — | Country resolves via runner |
| `role` | role name | `highlight` | Drives `role.core` / `role.glow` from tokens |
| `color` | hex | role core | Overrides core stroke color |
| `glowColor` | hex | role glow | Halo drop-shadow color |
| `fadeIn` | seconds | `0.4` | Entrance fade (≤0.4s), then static |
| `effect` | string | `border-neon` | Set explicitly; default for `applyBorder` |

---

### `advanceFront` — progressive invasion fill

Territorial advance: a region fills and grows along a soft glowing front.
Progress keyframes are **relative to the action's `at` time**. Driven from
runtime scene time (`MapEffects._currentT`) — works in realtime and
deterministic `stepTo` modes.

```json
{
  "at": 2.0,
  "action": "advanceFront",
  "params": {
    "id": "inv1",
    "country": "Ukraine",
    "geojsonSource": "inv1-geo",
    "from": [37.5, 47.9],
    "progress": [
      { "t": 0, "v": 0 },
      { "t": 4, "v": 0.45 },
      { "t": 7, "v": 0.6 }
    ],
    "role": "threat",
    "front": { "softness_px": 14, "glow": true },
    "easing": "easeInOut"
  }
}
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `id` | string | required | Unique front id |
| `country` / `geojson` | string / object | — | Polygon to clip; use `geojsonSource` if a prior `applyFill` resolved the country |
| `from` | `[lng, lat]` | — | Geodesic circle origin (mutually exclusive with `edge`) |
| `edge` | `east` \| `west` \| `north` \| `south` | — | Half-plane sweep from that edge |
| `progress` | `[{t, v}]` | `[{t:0,v:0}]` | `v` = fraction of country area (0–1) |
| `role` | role name | `threat` | Fill + front glow colors |
| `front.softness_px` | number | `14` | Edge blur radius |
| `front.glow` | boolean | `true` | Role-colored halo on front stroke |
| `easing` | easing name | `easeInOut` | Between progress keyframes |

#### `updateFront`

Append or replace progress keyframes on an active front:

```json
{
  "at": 14.0,
  "action": "updateFront",
  "params": {
    "id": "inv1",
    "progress": [{ "t": 7, "v": 0.6 }, { "t": 11, "v": 0.72 }]
  }
}
```

#### `removeFront`

Fade out and remove the front overlay. Schedule downstream actions ≥
`exitDuration` later (default `timing.exit_ratio × duration` or 0.6s).

```json
{
  "at": 22.0,
  "action": "removeFront",
  "params": { "id": "inv1", "exitDuration": 0.8 }
}
```

---

### `morphTerritory` — animate border change between map versions

Flubber interpolation between the largest outer rings of two country geometries.
**Limitation:** multipolygons use the single largest polygon only; islands and
exclaves in secondary polygons are ignored.

```json
{
  "at": 8.0,
  "action": "morphTerritory",
  "params": {
    "id": "morocco-morph",
    "fromSource": "mor-morph-from",
    "toSource": "mor-morph-to",
    "version_from": "latest",
    "version_to": "ceasefire",
    "duration": 4.0,
    "role": "contested",
    "easing": "easeInOut"
  }
}
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `id` | string | required | |
| `geojson_from` / `geojson_to` | object | — | Pre-resolved geometries |
| `fromSource` / `toSource` | string | — | Read geojson from a prior `applyFill` source id |
| `country` + `version_from` / `version_to` | string | — | Resolved by runner when W14 resolver covers morph actions |
| `duration` | seconds | `2` | Morph duration from action `at` |
| `role` | role name | `contested` | Fill color during morph |

`removeMorphTerritory` — same exit pattern as `removeFront`.

---

### Pattern fills (`applyFill`)

Add `pattern` to `applyFill` for contested / danger-zone conventions:

```json
{
  "at": 6.0,
  "action": "applyFill",
  "params": {
    "id": "wsahara-hatch",
    "country": "W. Sahara",
    "role": "contested",
    "pattern": "hatch",
    "opacity": 0.7,
    "effect": "fill-fade",
    "duration": 1.0
  }
}
```

| `pattern` | Description |
|---|---|
| `hatch` | 45° lines at role color over transparent |
| `gradient-radial` | role.core → transparent radial |
| `gradient-linear` | role.core → transparent diagonal linear |

Combinable with `fill-contested` effects and `role` colors.

---

### `maskImage` — photo/flag clipped to country shape

SVG `<image>` inside a country `clipPath`. Optional Ken Burns pan is
runtime-t-driven (deterministic-safe).

```json
{
  "at": 10.0,
  "action": "maskImage",
  "params": {
    "id": "algeria-flag",
    "country": "Algeria",
    "geojsonSource": "alg-mask-geo",
    "image": "../../assets/icons/circle-flags/dz.svg",
    "fit": "cover",
    "opacity": 0.85,
    "pan": { "duration": 10, "dx": 0.12, "dy": 0.06 }
  }
}
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `id` | string | required | |
| `country` / `geojson` | string / object | — | Clip outline |
| `geojsonSource` | string | — | Prior `applyFill` id when runner has not resolved `country` |
| `image` | path or URL | required | Local path relative to `map.html` or absolute URL |
| `fit` | `cover` \| `contain` | `cover` | SVG preserveAspectRatio |
| `opacity` | 0–1 | `0.9` | |
| `pan.duration` | seconds | `8` | Pan cycle length |
| `pan.dx` / `pan.dy` | fraction of bbox | `0.08` / `0.05` | Pan amplitude |

`removeMaskImage` — fade out and remove.

---

### Event metadata (W13 sound pass)

| Action | `type` | `intensity` |
|---|---|---|
| `advanceFront` / `updateFront` | `fill` | `0.9` |
| `applyBorder` (border-neon) | `border` | `0.5` |
| `morphTerritory` | `fill` | `0.7` |
| `maskImage` | `image` | `0.6` |

Attached via `fn.eventMeta` on each registered action (read by W13 emitter).

---

### QA scene

`scripts/map/qa_territory.json` — 25s deterministic showcase: border-neon Morocco,
advanceFront Ukraine (3 keyframes), morphTerritory latest↔ceasefire, hatch W. Sahara,
maskImage Algeria flag, flyTo at t=12 for reprojection proof.

```bash
python pipeline/render.py scripts/map/qa_territory.json qa_territory
```


## W12 — Map flow, text, and icons (fragment)

Merge into `map_renderer/docs/SKILL.md` at integration. Documents arrow styles, supply
lines, leader labels, counters, title cards, stat boxes, and geo icons.

---

### `drawArrow` — styles `taper` and `arc`

Extends the existing `drawArrow` action. All styles draw on from origin → destination;
use `removeArrow` to erase on exit.

#### `style: "taper"` — military advance (genre signature)

Thick at origin, tapering to the head, gentle curve, filled polygon with token glow halo.

```json
{
  "at": 0.5,
  "action": "drawArrow",
  "params": {
    "id": "advance",
    "from": [-6.84, 34.02],
    "to": [-13.2, 27.15],
    "style": "taper",
    "width_px": 30,
    "role": "threat",
    "wobble": true,
    "arc": 55,
    "duration": 2.8,
    "curved": true
  }
}
```

| Param | Default | Notes |
|---|---|---|
| `width_px` | `24` | Base width at origin (px) |
| `role` | `threat` | Token role color + glow |
| `wobble` | `false` | Subtle organic curve (`true` or amplitude number); seeded via `_seed` |
| `arc` | `80` | Bezier bow (px) |
| `duration` | `1.8` | Draw-on seconds |

#### `style: "arc"` — great-circle route

Great-circle interpolation (`turf.greatCircle`) with altitude-style bow; optional travel dot.

```json
{
  "at": 1.0,
  "action": "drawArrow",
  "params": {
    "id": "transatlantic",
    "from": [2.35, 48.86],
    "to": [-77.04, 38.91],
    "style": "arc",
    "role": "ally",
    "bowScale": 0.18,
    "travelDot": true,
    "headed": true,
    "duration": 3.0
  }
}
```

| Param | Default | Notes |
|---|---|---|
| `bowScale` | `0.15` | Midpoint bow as fraction of chord length |
| `travelDot` | `false` | Animate dot along arc after draw-on |

---

### `supplyLine` — flowing dashed logistics route

```json
{
  "at": 2.0,
  "action": "supplyLine",
  "params": {
    "id": "supply-route",
    "points": [[-7.59, 33.57], [-8.0, 31.63], [-9.6, 30.43], [-13.2, 27.15]],
    "role": "contested",
    "speed": 72,
    "style": "dashed",
    "duration": 1.0
  }
}
```

| Param | Default | Notes |
|---|---|---|
| `points` | — | `[[lng,lat], ...]` waypoints (≥ 2) |
| `role` | `neutral` | Stroke color from tokens |
| `speed` | `60` | Dash flow speed (px/s); deterministic mode derives offset from scene `t` |
| `style` | `dashed` | `dashed` \| `dotted` |

Remove with `removeSupplyLine` (same `exitDuration` semantics as `removeArrow`).

---

### `showLabel` — leader line + counter

#### Leader line (lower-third callout)

Label box floats above the anchor; 1px connector draws on to `leader.to`.

```json
{
  "at": 3.0,
  "action": "showLabel",
  "params": {
    "id": "city-callout",
    "text": "CASABLANCA",
    "position": [-7.59, 33.57],
    "role": "highlight",
    "effect": "label-fade",
    "duration": 0.7,
    "leader": { "to": [-7.59, 33.57], "style": "thin" }
  }
}
```

Box + leader reproject together on camera moves.

#### Counter (deterministic-safe)

Displayed value is derived from scene time in deterministic renders (mono digits).

```json
{
  "at": 5.0,
  "action": "showLabel",
  "params": {
    "id": "troop-counter",
    "text": "",
    "position": { "x": 0.72, "y": 0.22, "unit": "frac" },
    "role": "threat",
    "counter": {
      "from": 0,
      "to": 2300000,
      "duration": 3.0,
      "format": "short",
      "suffix": " troops"
    }
  }
}
```

| `counter.format` | Example output |
|---|---|
| `raw` | `2300000` |
| `comma` | `2,300,000` |
| `short` | `2.3M` |

---

### `titleCard` — kinetic chapter cards

Full-frame display-font card. Auto-exits after `hold_s` using `exit_ratio` timing.

```json
{
  "at": 8.0,
  "action": "titleCard",
  "params": {
    "id": "chapter-1939",
    "text": "1939",
    "sub": "THE SIEGE BEGINS",
    "role": "highlight",
    "effect": "letterbox",
    "hold_s": 3.0,
    "duration": 0.75
  }
}
```

| `effect` | Behavior |
|---|---|
| `slam` | Scale snap entrance |
| `cut` | Instant appear |
| `letterbox` | Surface bars sweep in; text between |

Emits event type `chapter` intensity `1.0`.

---

### `statBox` — flag/icon stat panel

Fixed-position panel; rows stagger via `stagger_ms` token.

```json
{
  "at": 10.0,
  "action": "statBox",
  "params": {
    "id": "forces",
    "title": "FORCES IN THEATER",
    "position": { "x": 0.04, "y": 0.1, "unit": "frac" },
    "rows": [
      { "flag": "ma", "icon": "shield", "iconPack": "lucide", "label": "Royal Army", "value": "120K" },
      { "icon": "users", "label": "Allied", "counter": { "from": 0, "to": 45000, "duration": 2.5, "format": "comma" } }
    ]
  }
}
```

- `icon` resolves from `assets/icons/<pack>/icons/<name>.svg`
- `flag: "ma"` resolves from `assets/icons/circle-flags/ma.svg`

---

### `showIcon` — geo-pinned SVG icon

```json
{
  "at": 11.0,
  "action": "showIcon",
  "params": {
    "id": "pin-rabat",
    "position": [-6.84, 34.02],
    "icon": "map-pin",
    "iconPack": "lucide",
    "role": "threat",
    "lift": true,
    "size": 32
  }
}
```

`lift: true` adds drop-shadow separation. Reprojects with camera like labels.

---

### Event metadata (sound pass)

| Action | `type` | `intensity` |
|---|---|---|
| `drawArrow` | `arrow` | `0.8` |
| `supplyLine` | `arrow` | `0.5` |
| `showLabel` | `label` | `0.4` |
| `showLabel` + `counter` | `counter` | `0.6` |
| `titleCard` | `chapter` | `1.0` |
| `statBox` | `callout` | `0.6` |
| `showIcon` | `image` | `0.4` |

Attached via `fn.eventMeta` on each registered action (read by `runtime.js` emitter).


## W13 — Camera language, atmosphere, vertical format, events/layout emission

New scene grammar from the W13 lane. Verified against
`map_renderer/web/js/effects/{camera,atmosphere}.js`,
`map_renderer/web/js/core/{utils,reproject,runtime}.js`,
`map_renderer/web/css/atmosphere.css`, and `map_renderer/runner.py`.
Everything below works in **both** render modes (realtime WebM and deterministic
`stepTo`).

---

### Camera easing presets

`flyTo` (and the opening `camera`) gain an `easing` preset that shapes the move.
The same curve is used in realtime (Mapbox `flyTo` easing) and deterministic
camera stepping, so arrivals look identical in both modes.

| Preset | Feel | Use for |
|---|---|---|
| `swoop` | fast depart, long decelerate | cinematic arrival onto a region |
| `ramp` | slow → fast → snap → slow | energetic push between two beats |
| `gentle` | soft symmetric ease | calm repositioning, orbits |
| `linear` | constant speed | mechanical / measured moves |
| `easeInOut` | cubic in-out (legacy default) | back-compat; the default if omitted |

```json
{ "at": 0.5, "action": "flyTo", "params": {
    "center": [-4.0, 30.5],   // [lng, lat]
    "zoom": 4.4, "pitch": 45, "bearing": 0,
    "duration": 2.5,
    "easing": "swoop"          // swoop | ramp | gentle | linear | easeInOut
} }
```

The opening `camera` block accepts `easing` too: `"camera": { ..., "easing": "swoop" }`.

---

### `rotateAround` — bearing orbit around a pinned point

Orbits the camera bearing around a fixed center; pitch and zoom are held. The
genre "circle the capital" move.

```json
{ "at": 8.0, "action": "rotateAround", "params": {
    "center": [-6.84, 33.97],  // pinned orbit center [lng, lat]
    "degrees": 40,             // bearing change over the move (+ = clockwise)
    "duration": 3.0,
    "easing": "gentle"
} }
```

Emits a `camera` event (start/end pair). Deterministic: realized as a camera-plan
segment; realtime: `map.easeTo` with the matching easing.

---

### `idle_drift` — "the map always breathes"

Scene-level key (not a timeline action). A continuous, subtle push-in + bearing
drift applied **whenever no explicit camera action is active** — it suspends
during a `flyTo`/`rotateAround` and resumes after, composing additively.

```json
"idle_drift": { "enabled": true, "zoom_per_s": 0.004, "bearing_per_s": 0.1 }
```

- `zoom_per_s` — zoom added per idle second (0.004 ≈ very subtle push-in).
- `bearing_per_s` — degrees of bearing added per idle second.

Deterministic-safe: the offset is derived from elapsed idle time, so a given `t`
always yields the same camera. Bump the rates (e.g. `0.03` / `1.0`) to make the
drift obvious during a long hold.

---

### Atmosphere & terrain

Scene-level keys, applied on style load. Colors are token-tinted (palette).

```json
"atmosphere": { "fog": true, "stars": false },   // horizon/space glow; stars in space
"terrain":    { "enabled": true, "exaggeration": 1.4 }  // Mapbox DEM + setTerrain
```

- `atmosphere.fog` — enables `setFog` (token-tinted horizon + space color).
- `atmosphere.stars` — adds star intensity in the space band (visible when zoomed
  out enough to see the globe edge / space).
- `terrain.enabled` — adds the `mapbox-dem` source and elevates the surface;
  combine with `pitch` for the parallax/depth look. `exaggeration` defaults `1.4`.

**Clean base lines (opt-in).** The base style draws sub-national (province /
admin-1) boundary lines that pop in at zoom thresholds. To suppress them for a
clean canvas while keeping country outlines + coastlines:

```json
"base": { "internal_borders": false }   // default (absent/true) = leave base lines as-is
```

This only hides base **line** layers; it does not touch your own drawn borders.

---

### `extrudeBars` — extruded columns comparing a metric

Per-country 3D columns (Mapbox `fill-extrusion`) whose height encodes a value.
Country geometry is resolved by the runner (like `applyFill`); pass either
`country` (resolved) or pre-resolved `geojson` per bar.

```json
{ "at": 4.0, "action": "extrudeBars", "params": {
    "id": "metric",
    "max_height_m": 300000,    // height (metres) of the largest value
    "role": "threat",          // column color from palette.roles.<role>.core
    "duration": 1.2,           // grow-in time in seconds (default 1.0)
    "easing": "easeInOut",     // grow curve (default easeInOut) — see easing presets
    "fade_in": 0.3,            // optional: opacity fade-in time (default ~25% of duration)
    "data": [
      { "country": "Morocco", "value": 100 },
      { "country": "Algeria", "value": 65 },
      { "country": "Spain",   "value": 40 }
    ]
} }
```

The bars **grow in** from flat to full height over `duration`, using the same
easing presets as the camera (`easeInOut` default = smooth start *and* settle, so
the columns ease up from the ground rather than snapping). They also **fade in**:
opacity ramps 0→full over the first `fade_in` (default ~25% of `duration`) so the
footprint materializes softly instead of popping at full color. The fade is
front-loaded on purpose — opacity reaches full while the bars are still nearly
flat, avoiding Mapbox's see-through fill-extrusion artifact on tall geometry.
Everything is t-driven so realtime + deterministic match. Heights scale linearly
to `value / max(values) * max_height_m`. Needs a pitched camera to read as 3D.
Emits a `fill` event.

**`removeExtrudeBars`** shrinks the columns back to flat, then removes them:

```json
{ "at": 10.7, "action": "removeExtrudeBars", "params": {
    "id": "metric",       // matches the extrudeBars id
    "exitDuration": 1.0   // shrink-out time in seconds (default 1.0)
} }
```

> Authoring note: base place labels (see `showPlaceLabels`) render **beneath** the
> 3D extrusion layer, so a bar will occlude a city/country label it overlaps. Don't
> overlap base labels with bars — reveal labels before the bars grow or after they
> shrink out, or use your own overlay labels (always on top).

---

### Polish stack (vignette / grain / haze)

A CSS overlay above the map, below labels. Defaults: vignette + grain **on**
(intensity from the grading tokens), haze **off**. Grain shimmers in an 8-step
loop and haze pans slowly — both driven by runtime `t` (deterministic).

```json
"polish": { "vignette": true, "grain": true, "haze": false }
```

Opacities come from `config/design_tokens.json` → `grading.vignette_opacity` /
`grading.grain_opacity` (never hardcode them in a scene).

---

### Vertical format + safe areas

```json
"format": "vertical"   // "vertical" (1080×1920) | "horizontal" (1920×1080, default)
```

The runner sizes the viewport/recording and the page to the format; the rendered
MP4 matches (vertical = 1080×1920). `window.sceneFormat` exposes the current
format to overlay modules.

**Fraction-based screen positions.** Screen-fixed positions may be given as
fractions of the frame instead of pixels (pixels still work for back-compat):

```json
"position": { "x": 0.5, "y": 0.1, "unit": "frac" }   // → centre, 10% down
```

This lane ships the resolver (`MapEffects.layoutHints.resolvePosition`); the text
modules (labels / statBox / titleCard) consume it in the flow-text lane (W12). Use
pixel positions in map scenes until that lands.

**Safe areas.** `MapEffects.layoutHints` (in `core/utils.js`) exposes
`format()`, `frameSize()`, `safeRect()` (usable px rect inside the platform
margins and above the caption band, from `design_tokens.safe_areas`), and
`resolvePosition()` (frac→px). Text modules use it to keep callouts/labels out of
the caption band. When authoring vertical scenes by hand, keep screen-fixed
labels above the caption band (`safe_areas.vertical.caption_band`, default
`[0.78, 0.92]`) and inside the platform margins.

---

### `showPlaceLabels` — re-enable base-map labels

By default **all** base-style symbol layers (place names + icons) are hidden so
only your own overlay labels show. `showPlaceLabels` re-enables selected base
layers. Your overlay labels are unaffected.

```json
{ "at": 9.8, "action": "showPlaceLabels", "params": {
    "show": true,
    "types": ["country", "city"],   // country | state | city | water
    "within": [-12, 27, 4, 37]      // optional bbox [w, s, e, n] to scope the reveal
} }
```

Note: `within` replaces the matched layers' own filters (a documented
limitation) — fine for scoping a reveal to a region.

---

### Sidecar files: events.json & layout.json

Every render now writes two sidecars next to the MP4 (`output/<clip>.events.json`,
`output/<clip>.layout.json`), conforming to `docs/contracts/{events,layout}.schema.json`.

**`events.json`** — one entry per executed action (and a start/end pair for camera
actions). Consumed by the sound pass.

```json
{ "clip_id": "qa_camera", "fps": 20, "events": [
  { "t": 0.5, "type": "camera", "phase": "start", "intensity": 0.5, "id": "flyTo-0.5" },
  { "t": 3.0, "type": "camera", "phase": "end",   "intensity": 0.5, "id": "flyTo-0.5" }
] }
```

Each action contributes its `eventMeta` (`type`, `intensity`); unmarked actions
fall back to `type: "label"`, `intensity: 0.4`. This lane's actions emit:
`flyTo`/`rotateAround` → `camera` 0.5, `cameraShake` → `camera` 0.6,
`extrudeBars` → `fill` 0.7, `showPlaceLabels` → `label` 0.4.

**`layout.json`** — overlay box occupancy sampled at 2 Hz, used for caption
placement (so captions avoid on-screen text).

```json
{ "clip_id": "qa_camera", "format": "horizontal", "sample_hz": 2, "frames": [
  { "t": 0.5, "boxes": [ { "id": "qa-title", "kind": "label",
      "x": 0.45, "y": 0.06, "w": 0.10, "h": 0.04 } ] }
] }
```

Box coords are normalized (top-left origin, `[0,1]`). `kind` comes from a
`data-kind` attribute (set via `MapEffects.createOverlayEl`) or is inferred from
the element's class. Geo SVG paths (arrows/fills/borders) are excluded — only
screen-occupying overlays (labels/callouts/stat boxes/images) are sampled.


## W14 — Map catalog discovery and version resolver

Fragment for merge into `map_renderer/docs/SKILL.md` at integration.

### Manifest lockfile

`map_renderer/data_prep/map_versions.json` is a **lockfile** — tooling writes it via
`--add` / `--add-all`; do not hand-edit entries. Every entry carries mandatory
provenance fields: `license`, `license_url`, `commercial_ok` (bool), `added_by`.

### CLI: discover, add, audit

```bash
## List datasets in a catalog
python -m map_renderer.data_prep.prepare_maps --discover natural_earth
python -m map_renderer.data_prep.prepare_maps --discover historical_basemaps
python -m map_renderer.data_prep.prepare_maps --discover cshapes

## Add one dataset → manifest entry + download + process
python -m map_renderer.data_prep.prepare_maps \
  --add natural_earth:ne_10m_admin_0_disputed_areas --version disputed

## Bulk-add every dataset from a catalog
python -m map_renderer.data_prep.prepare_maps --add-all natural_earth

## List non-commercial versions present in manifest / local data
python -m map_renderer.data_prep.prepare_maps --audit

## Legacy prepare (unchanged)
python config/prepare_maps.py --from-manifest --version latest
```

`--version` on `--add` sets the manifest key (default: dataset id).

### Catalogs

| Catalog | Source | `commercial_ok` |
|---------|--------|-----------------|
| `natural_earth` | NACIS S3 CDN (`naturalearth.s3.amazonaws.com`) | `true` (public domain) |
| `historical_basemaps` | [aourednik/historical-basemaps](https://github.com/aourednik/historical-basemaps) GeoJSON by year | `false` (GPL-3.0; data terms ambiguous) |
| `cshapes` | CShapes 2.0 GeoJSON (ETH Zurich) | `false` (CC BY-NC-SA 4.0) |

Natural Earth covers cultural admin families at 10m / 50m / 110m. `populated_places`
uses the `places` processing recipe (`places.featurecollection.geojson`); all others
use `countries` (`countries.featurecollection.geojson` + per-country slugs).

Historical basemaps version keys: `world_{year}` (e.g. `world_1900`).

### Year resolution

Scene or action `version` strings that are **four-digit years** (e.g. `"1942"`) resolve
to the nearest available `world_YYYY` manifest key **≤ that year**:

```
1942 → world_1938 (nearest available)
```

Exact-name resolution is unchanged for non-year strings. Alias map (`map_aliases.json`)
is applied first.

### `commercial_ok` semantics

- **`commercial_ok: true`** — no restriction; Natural Earth (PD) entries.
- **`commercial_ok: false`** — data loads normally but the resolver logs a prominent
  `NON-COMMERCIAL MAP DATA` warning. Run `--audit` to list non-commercial versions
  present locally.

### Miss behavior (orchestrator contract)

Unknown version resolution order:

1. Alias (`map_aliases.json`)
2. Year → nearest `world_YYYY`
3. Manifest hit → auto-provision if missing on disk
4. Catalog discovery (exact `dataset_id` match) → auto-add + download
5. **Miss** → `MapVersionNotFoundError` with `suggestions: list[str]` (up to 5 nearest
   manifest keys by string similarity + year proximity)

W20 orchestration catches `MapVersionNotFoundError` and reads `.version` and
`.suggestions` for machine-readable recovery hints.

Known manifest keys whose provision fails still fall back to `latest` with a warning;
unknown names never silently fall back.


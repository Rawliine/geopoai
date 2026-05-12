# map_animation_skill — LLM Guide to Authoring Scene JSON

This file teaches an LLM how to write scene JSON files for the GeoPoAI renderer.
Tone: be precise, use the exact key names, default to safe choices.

---

## What the renderer does

The renderer reads a **scene JSON file**, drives a headless Mapbox GL JS browser page
via Playwright, and produces an MP4. A scene is a sequence of timed actions that add
fills, borders, arrows, labels, and pulse effects to a map.

The Python entry point is `pipeline/render_scene.py`. It resolves `country:` shorthands
to GeoJSON, then passes the full scene to the browser. All visual logic lives in
`renderer/effects.js` / `renderer/effects.css`.

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
    "width": 4,                 // stroke width in px (default 2.5)
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

**Important:** `arrow-travel` with `headed: true` places the arrowhead at the
destination while the dot is still traveling — usually looks wrong. Use
`"headed": false` for travel arrows.

All arrow types now have a draw-on entrance (path traces from origin to destination
before the main effect starts). Budget ~0.25–0.35× `duration` for the entrance.

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

Available versions are listed in `data/maps/versions.json`.
Aliases (like `"ceasefire"` → `"1991_ceasefire"`) are in `data/maps/aliases.json`.

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
   frame-rate variation). Infinite CSS effects (`border-glow`, `border-marching`,
   etc.) run correctly in both modes.

7. **Total duration.** Set `duration` (top-level) at least 0.5s beyond the last
   action's `at` + its animation duration. The clip cuts abruptly at `duration`.

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
        "color": "#c0392b", "width": 4, "effect": "arrow-travel",
        "curved": true, "arc": 110, "headed": false, "duration": 3.8, "delay": 0 }
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

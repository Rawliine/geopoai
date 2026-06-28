# W26 — Map media: reserved-region box (post-composition) + active safe-area enforcement

Branch: `agents/w26-map-media` · Depends on: W11 (`maskImage`, merged) + W14 (resolver,
merged) + W17 (composition engine, merged). Runs **before** W20 (the integrator consumes
this contract).

> **Re-scope (validated 2026-06-28).** This supersedes the original W26 (browser-drawn
> media boxes + clip-to-border **video**). See "What changed and why". 3D models (W22) are
> deferred — see `plans/PLAN.md` backlog.

## What changed and why
The original W26 drew media boxes — and decoded **video** — inside the headless browser
during deterministic frame-stepping. An HTML5 `<video>` can't be advanced frame-accurately
by `stepTo`, so it produced blank frames; and a screen-space box has no reason to live in
the geo-anchored renderer at all. Decision: **screen-anchored media is composited in post.**
The map renderer's only jobs are (a) keep its own globe-framing and on-screen text **out of**
the reserved region, and (b) **emit** the reserved windows so composition knows where/when to
drop media. No box is ever drawn in the browser (no placeholder rectangle either).

Clip-to-border **images** already ship (`maskImage`, W11) and are **untouched** (the
"2b" path). Clip-to-border **video** (old "2c") is **dropped**.

This is a single cross-layer lane (map + composition) by design: its entire value is the
renderer→composition handshake (emit windows → overlay into exactly those windows), so one
author owns both sides of the seam. There is no concurrent lane to conflict with — W20 is
sequential after this.

## Contract (lead pre-creates — frozen, never edit in-lane)
Like the original W26's `map.html`/schema pre-step:
- Scene schema: `reserveRegion` / `releaseRegion` timeline-action block (region addressing +
  time window) in `map_renderer/schema/scene.schema.json`.
- A new **empty** `map_renderer/web/js/effects/media.js` + its `<script>` tag in
  `web/map.html` (no media.js or tag exists on `main` today).
- Compose schema: a `media_overlays[]` entry (`{ src, region|rect, start, end, fit:"contain",
  border?, caption? }`) in `docs/contracts/compose.schema.json`.

## Allowlist
`map_renderer/web/js/effects/media.js` (fill the stub) · `map_renderer/web/css/media.css`
(new) · the map safe-area / layout touchpoints in `map_renderer/web/js/core/` +
`map_renderer/runner.py` (reserved-window sidecar) · `composition/media_overlay.py` (new) ·
`pipeline/compose.py` (wire the pass) · `scripts/map/` (demo) ·
`map_renderer/docs/fragments/w26-map-media.md` (new) + a `composition/README.md` note.

## Read first
`map_renderer/web/js/core/reproject.js` (`_maybeSnapshotLayout` — the 2 Hz occupancy
sampler; the reserved-window emission rides alongside it) · the **map caption-band / safe-area
exclusion** (W12/W13 — locate the exact hook screen-space labels respect; the reserved band
generalizes it) · `map_renderer/runner.py` sidecar emission (events.json / layout.json) ·
`composition/engine.py` + `composition/transitions.py` (where the burn/overlay passes plug in,
and the NVENC/libx264 encode policy) · `composition/README.md` (pass order) · `fills.js`
`maskImage` (the untouched 2b path, for contrast — do **not** edit it).

## Checklist

### T1 — `reserveRegion` / `releaseRegion` (map, deterministic, draws nothing)
Fill `media.js`: `reserveRegion { id, region: "top"|"bottom"|"lower-third"|{rect}, at,
duration, ramp? }` activates a **time-windowed** exclusion band; `releaseRegion` (and
auto-expiry at `at+duration`) ends it. Nothing visible is drawn. Driven purely by runtime
`t` so it behaves identically under `stepTo` (deterministic) and the realtime loop;
token-timed in/out `ramp`. `fn.eventMeta = { type: "region", intensity: ... }`.

### T2 — Active safe-area enforcement
Generalize the existing caption-band exclusion so screen-space overlays (titles, labels,
lower-thirds, the caption band) are kept **out of** an active reserved band, re-solved per
frame so displaced text **eases** out as the band ramps in and re-flows after it releases
(never an instant jump — standing in/out rule). Geo-anchored content (the globe, pinned
country labels) is **not** moved by the renderer — the camera framing that puts the globe in
the complementary area is authored (storyboard/LLM); the layout sidecar (T3) lets QC catch
geography bleeding into the band.

### T3 — Reserved-window sidecar
`runner.py`: emit the active reserved windows as `[{ id, rect, start, end }]` (in
frame/screen coordinates composition can consume directly) into a sidecar, extending the
existing emitter. Deterministic — derived from the same `t` walk as events/layout.

### T4 — Composition media-overlay pass
`composition/media_overlay.py`, wired into `pipeline/compose.py`: overlay each
`media_overlays[]` entry onto the assembled clip over `[start, end]` only — **contain-fit +
letterbox** (no stretch), token-styled border, optional caption — via ffmpeg
(`h264_nvenc`/`libx264` per the existing export policy). Idempotent and individually
skippable like the other passes. **No video decode in the browser.** Reads the overlay specs
from the compose spec; the renderer's reserved-window sidecar is the cross-check that placement
matches what the map kept clear.

### T5 — Demo + docs fragment
A `scripts/map/` scene with a `reserveRegion` window (top half, `[t1, t2]`) paired with a
camera move framing the globe **below** the band, rendered **deterministically** — verify
on-screen text stays out of the band during the window and re-flows after, and that the
sidecar lists the window. Plus a small `compose` run overlaying a sample video into that
window. `docs/fragments/w26-map-media.md`: `reserveRegion`/`releaseRegion` params, the
compose `media_overlays` shape, and the **authoring note** that a reserve window must be
paired with a camera move that frames the globe into the complementary area.

## Out of scope
3D models (W22, deferred) · clip-to-border **video** (old 2c, dropped) · editing
`maskImage` / `fills.js` (2b ships as-is) · orchestration routing (W20) · drawing **any**
box or placeholder rectangle in the browser.

## Acceptance
Deterministic map render: on-screen text stays clear of the reserved band throughout its
window and re-flows afterward; the reserved-window sidecar lists `{ id, rect, start, end }`.
A `compose` run overlays a video into that window (contain-fit, no stretch, token border)
over `[start, end]` **only**. `maskImage` behavior unchanged; scene + compose schemas
validate; pytest green.

# W26 — Map media frames: reserved-region box + clip-to-border media

Branch: `agents/w26-map-media-frames` · Depends on: W11 (maskImage, merged) + W14
(country resolver, merged) — runs in parallel with W24/W25/W27.

## Goal
Two ways to put an image **or video** onto a map scene, both **contain-fit** (no
stretch), driven by the LLM/storyboard:

- **Reserved-region box** — pin a media box to a screen region (e.g. top half) while
  the globe/map occupies the rest; the box has a token-styled border and fits the
  media inside. (`map_region` input use.)
- **Clip-to-border** — clip media to a resolved country/region geometry (the
  Algeria-flag treatment, now for any media incl. video). (`map_mask` input use.)

Implemented in a **new effect file** so it never edits W11's `fills.js`; the
clip-to-border path **reuses** maskImage's geometry/clip approach (rings from the
resolver) rather than modifying it.

## Allowlist
`map_renderer/web/js/effects/media.js` (new) · `map_renderer/web/css/media.css`
(new) · `map_renderer/docs/fragments/w26-map-media.md` (new) · `scripts/map/`
**Lead pre-creates (shared files, W00-style):** the `<script src="js/effects/media.js">`
tag in `web/map.html` and a `media` action stub block in
`map_renderer/schema/scene.schema.json`.

## Read first
`map_renderer/web/js/effects/fills.js` (`maskImage`, `_maskImageBounds`, rings/clip)
· `map_renderer/resolver.py` (country → geometry) · `web/js/core/` (overlay element
helpers, deterministic `stepTo`) · `map_renderer/docs/SKILL.md` · the W11 masked-image
docs

## Checklist

### T1 — Reserved-region media box
`media.js` registers `showMediaFrame`: params `{ id, src, region: "top"|"bottom"|
"left"|"right"|{rect}, fit:"contain", border?, caption? }`. Positions a fitted media
box in the screen region (safe-area aware), letterboxed; map camera/layout unaffected
(operator frames the globe into the complementary half). Token-styled. In/out anim.

### T2 — Clip-to-border media
`maskMedia`: clip an image/video to a resolved country/region shape — reuse the
maskImage ring/clipPath approach (call the resolver for geometry); add **video**
support (the only thing maskImage lacks). Optional slow pan. Reprojects on camera
move (deterministic-safe, like the W11 fix).

### T3 — Schema + tokens + removal
Fill the lead-stubbed `scene.schema.json` media section (params + validator);
`removeMediaFrame`/`removeMask` for clean exits; all colors/border/letterbox from
`config/design_tokens.json` via CSS vars — no hardcoded values.

### T4 — Fragment + deterministic demo
`docs/fragments/w26-map-media.md` (both actions) + a `scripts/map/` demo rendered
**deterministically**: a video in a top box with the globe below, and an image
clipped to Morocco. Verify the rendered frames yourself.

## Out of scope
Orchestration / routing (W20) · editing `fills.js` / `borders.js` / `arrows.js` /
`labels.js` internals · W22 3D models · manim media (W25).

## Acceptance
Deterministic demo shows (a) media fit inside a top-half box with the map below and
(b) media clipped to a country border, both formats, no stretch; schema validates;
no edits to other lanes' effect files.

# W12 — Map: arrows, flow lines, labels, counters, title cards, icons

Branch: `agents/w12-flowtext` · Depends on: W00 + W02.

## Allowlist
map_renderer/web/js/effects/arrows.js · effects/labels.js ·
web/css/arrows.css · web/css/labels.css · scripts/map/qa_flowtext.json (new) ·
map_renderer/docs/fragments/W12.md (new)

## Read first
web/js/core/{registry,utils,reproject}.js (read-only) · effects/arrows.js ·
effects/labels.js · config/design_tokens.json · docs/contracts/events.schema.json

## Checklist

### T1 — Military advance arrow (the genre signature)
`drawArrow` gains `style: "taper"`: thick at origin, tapering to the head,
gentle curve, grows origin→target (animate via stroke-dash on a path whose
width is faked with a filled tapered polygon — compute polygon outline from
the centerline with width interpolation; utils.curvedPath gives the
centerline). Params: `width_px` (base), `role`, optional `wobble` (subtle
organic curve offset, seeded). Glow halo from tokens.

### T2 — Great-circle arcs + supply lines
- `style: "arc"`: great-circle interpolation between endpoints (turf
  greatCircle), rendered with altitude-style bow (scale the curve's
  midpoint offset with distance), draw-on animation, optional moving dot
  (reuse animateTravelDot).
- New `supplyLine` action: dashed polyline through waypoints, dashes
  flowing along the path continuously (`stroke-dashoffset` animation —
  deterministic mode must derive offset from runtime t). Params:
  `{ id, points: [[lng,lat]...], role, speed, style: "dashed"|"dotted" }`.

### T3 — Leader-line labels (lower-third style)
`showLabel` gains `leader: { to: [lng,lat], style: "thin" }`: label box
floats offset from its anchor with a 1px connector line down to the exact
point; line draws on entrance. Label box styling from tokens (surface bg,
role accent edge). Reprojection moves box + leader together.

### T4 — Count-up numbers
`showLabel` gains `counter: { from, to, duration, format: "comma|short|raw",
prefix, suffix }` using utils.animateCounter — but deterministic-safe:
derive displayed value from runtime t, not requestAnimationFrame wall time
(extend animateCounter with a progress-driven variant; wall-clock path stays
for realtime mode). Mono font (token) for digits to prevent jitter.

### T5 — Kinetic title cards ("1939", "THE SIEGE BEGINS")
New `titleCard` action: full-frame centered display-font card —
`{ text, sub?, role, effect: "slam"|"cut"|"letterbox", hold_s }`.
Letterbox variant: two horizontal bars sweep in (top/bottom), text between
them, bars at `surface` color. Auto-exit after hold_s with exit_ratio
timing. Emits event type "chapter" intensity 1.0 (fn.eventMeta — see W11.T6
mechanism).

### T6 — Stat box + flag chips
`statBox` action: small fixed-position panel `{ title, rows: [{icon?, flag?,
label, value, counter?}] }`, entrance stagger per row (`stagger_ms` token).
`icon:` names resolve from `assets/icons/<pack>/` (provisioned packs);
`flag: "ma"` resolves from circle-flags. New `showIcon` map action too:
geo-pinned SVG icon (data-lng/lat reprojection like labels), role-tinted
stroke, optional `lift` (drop-shadow separation per genre grammar).

### T7 — Event metadata + QA scene
`fn.eventMeta` on every action above (arrow 0.8, supplyLine 0.5, label 0.4,
counter 0.6, titleCard/chapter 1.0, statBox 0.6, icon 0.4).
`scripts/map/qa_flowtext.json`: taper arrow Rabat→Laayoune, arc
Paris→Washington, supplyLine 4 waypoints, leader label, counter label
(0→2,300,000 short format), titleCard letterbox, statBox with flags+icons,
one flyTo to prove reprojection. Deterministic, 25s.

### T8 — Docs fragment
`map_renderer/docs/fragments/W12.md`: taper/arc arrow styles, supplyLine,
leader labels, counter labels, titleCard, statBox, showIcon — full params +
one JSON example each, SKILL.md style.

## Out of scope
fills/borders (W11) · camera/atmosphere/vertical (W13) · core/*.js · map.html ·
caption rendering (composition lane).

## Acceptance
qa_flowtext renders deterministically; screenshots at t=3/8/14/21 in report;
counter value at mid-animation frame matches expected interpolation
(deterministic check: same frame twice → identical pixels); no console errors.

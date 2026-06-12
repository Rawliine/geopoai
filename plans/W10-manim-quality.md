# W10 — Manim engine: layout fixes, fonts, emission, pacing, new components

Branch: `agents/w10-manim` · Depends on: W02.

## Allowlist
manim_renderer/ (EXCLUDING escape_hatch/) · scripts/manim/ ·
pipeline/render_manim.py

## Read first
manim_renderer/scene.py · registry.py · schema/validator.py · theme/*.py ·
components/base.py · docs/contracts/{events,layout}.schema.json ·
config/design_tokens.json

## Checklist

### T1 — Font warning fix
Reproduce: render `scripts/manim/qa_showcase_v_2.json`, capture the font
warning/error from stderr (likely Pango fallback for Barlow Condensed or
STIX Two Math not installed system-wide). Fix properly: load font files from
`assets/fonts/` (provisioned by `tools/prepare_assets.py`) and register them
with `manim.utils.register_font` (or context-manager equivalent) inside theme
setup, so renders are font-correct on any machine without system installs.
Acceptance: warning gone from stderr; titles visibly condensed (Barlow).

### T2 — Reported layout bugs (one commit each, screenshot before/after)
a. PayoffMatrix: row-player labels (e.g. "Bob") too close vertically to
   strategy labels ("Cooperate") — add min-gap from a new theme spacing
   constant (token-derived), not a magic number.
b. BarChart/LineChart: axis title ("Quarter") nearly overlaps tick labels
   (Q1–Q4); y-axis title ("Sales") too close to tick numbers — same
   spacing constant.
c. Stacked layout (chart top + chart bottom): excessive inter-chart gap,
   most visible when callout-below-top and callout-above-bottom face each
   other — the layout solver should compress vertical slack so facing
   callouts sit within ~1.5× the standard gap.
d. General callout↔subject spacing: enforce one min/max gap pair from
   tokens across all callout placements.
Repro scenes: `qa_showcase_v_2.json` (~12s matrix; ~2:25 dual-chart),
`qa_mega_h.json`. Add a regression scene `scripts/manim/qa_spacing.json`
exercising a–d.

### T3 — events.json emission
In scene.py's action loop, emit one event per timeline action per
`docs/contracts/events.schema.json` (map component/action names → event
types; intensity heuristic: hero/primary role → 0.8, supporting → 0.5,
ambient → 0.2). Write `<output>.events.json` next to the MP4.
Acceptance: render hello.json → events.json validates against schema.

### T4 — layout.json emission
The runner re-solves layout on composition changes — at each solve (and at
sample_hz=2 between solves) record normalized bounding boxes of all visible
mobjects (id, kind from component class, x/y/w/h). Write `<output>.layout.json`
per the schema. Acceptance: validates; boxes match a spot-checked frame.

### T5 — Safe-area constraint
Layout solver treats `tokens.safe_areas[format].caption_band` plus
platform_margins as forbidden regions for ALL components (callouts
especially). Acceptance: render `qa_showcase_v_2.json`; no box in
layout.json intersects the caption band.

### T6 — Pacing checks in the validator
Extend schema/validator.py warnings: visual-change gap > `static_max_s`;
callout on screen < max(`callout_min_s`, chars/`read_rate_cps`); >3
simultaneous entrances; entrance stagger < `stagger_ms` when ≥2 components
enter in the same action. Warnings (stderr + returned report), not errors.

### T7 — Icon component
`showIcon` component (components/narrative/icon.py): loads SVG by name from
`assets/icons/<pack>/`, strokes tinted by `role` token, optional glow
(token radii), sizes from FONT_SCALE-relative units. Flags via circle-flags
pack: `icon: "flag:ma"`. Register in registry.py. Demo scene
`scripts/manim/qa_icons.json`.

### T8 — ImageCard component
components/narrative/image_card.py: framed image, slow Ken Burns drift
(direction/zoom params, never static), mandatory `source` param rendered as
small attribution chip (token caption size), optional `mask: "country:<name>"`
deferred to map side — here rectangular/rounded only. Register + demo scene
`qa_images.json` (use any local test image; document the path convention
`assets/images/` for episode-supplied images).

## Out of scope
escape_hatch/ · captions · sound · map anything.

## Acceptance (lane)
All qa_* scenes render clean; new regression scenes committed; events+layout
files validate; validator pacing warnings demonstrably fire on a crafted bad
scene (`qa_pacing_bad.json`, committed).

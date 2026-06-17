# GeoPoAI — Manim Layer Implementation Plan

Status: proposal, fluid. Phase boundaries are guidance, not deadlines.

---

## Target end state

A second rendering engine sitting alongside the existing Mapbox/Playwright pipeline. Both engines consume scene JSON and produce MP4 clips. An orchestrator (n8n / langgraph) composes a full video from multiple clips of either type, plus B-roll and audio. The LLM authors scene JSON against a constrained schema; coordinates and pixel positions never appear in the JSON.

```
LLM → scene JSON → pipeline/render.py (dispatcher)
                        ├── renderer="mapbox" → render_scene.py → existing engine
                        └── renderer="manim"  → render_manim.py → manim_renderer/
                                                                       ↓
                                                               JSONScene runner
                                                                       ↓
                                                                  MP4 clip
```

---

## Phase 0 — Foundation (≈1 week)

Goal: end-to-end "hello world" — JSON in, MP4 out, no real components yet.

- Add `manim>=0.18` to `requirements.txt`. Pin a version; Manim API drift is real.
- Create `manim_renderer/` skeleton (full layout below in AGENT.md).
- `pipeline/render.py` — unified dispatcher reading `"renderer"` field from JSON, calling the right backend.
- `pipeline/render_manim.py` — thin async wrapper that validates JSON, instantiates `JSONScene`, runs Manim, copies output to `output/`.
- `manim_renderer/theme/` — palette, typography, timing, easing. Palette must be diffed against `map_renderer/web/css/*.css` actor colors. Same hex codes everywhere.
- `manim_renderer/components/base.py` — `BaseComponent(VGroup)` abstract class. Methods: `build()`, `entrance(effect, timing)`, `exit(effect)`, `get_anchor(name)`, `measure()`.
- `manim_renderer/scene.py` — `JSONScene(MovingCameraScene)`. Reads JSON, sorts timeline, dispatches to component registry, manages `id → mobject` registry, handles inter-action waits.
- `manim_renderer/registry.py` — `REGISTRY: dict[str, type[BaseComponent]]`.
- `manim_renderer/layouts/` — base + resolver. Implement one layout (`hero`) for both horizontal and vertical to validate the system.
- `manim_renderer/schema/scene_schema.json` — top-level scene shape (format, layout, duration, timeline, slots, overlays). Validate on every render.
- One dummy component (`TextCard`) — fades in centered text. Enough to prove the pipeline runs.
- Smoke test: a `scripts/manim/hello.json` that renders a 3-second MP4 via `python pipeline/render.py scripts/manim/hello.json hello`.

Exit criteria: hello.json renders to MP4 in both horizontal and vertical. JSON schema rejects malformed input cleanly.

---

## Phase 1 — Core component library ✓ DONE

Status: **complete**. Exit criteria met — `scripts/manim/prisoners_dilemma.json` and
`prisoners_dilemma_vertical.json` render a 60-second narrative end-to-end using
only this library.

Shipped components (build order followed plan.md's spec):
1. **StatBlock** ✓ — value + label + optional unit/trend/sparkline; `count-up` entrance
2. **MetricGroup** ✓ — bundle of StatBlocks; row/column orientation; staggered entrance
3. **CalloutBox** ✓ — bubble + leader line via `position_finalized`; format-aware leader edges
4. **BarChart** ✓ — categorical bars; per-bar count-up + grow-up; palette color rotation
5. **LineChart** ✓ — continuous multi-series; `draw-out` (Create) path animation; series-end anchors
6. **Timeline** ✓ — single component, format-aware (L→R horizontal / T→B vertical with depth cap)
7. **GameTree** ✓ — recursive layered layout; vertical depth-capped; `node:<path>` anchors
8. **AllianceWeb** ✓ — deterministic circular layout (Phase 1 simplification, see handoff.md);
   alliance/rivalry/neutral edge kinds
9. **PayoffMatrix** ✓ — 2×2 through 6×6; cell/row/col anchors; level-by-level entrance
10. **TextCard** ✓ (from Phase 0; refactored to use base defaults in PR 1.0)

Layouts (5 per format, 8 total): `hero`, `split`/`stacked`, `data-left`/`data-top`,
`trio`/`trio-stack`, `title-body`. Format/layout compatibility enforced by validator.

Mutation actions: `removeComponent`, `highlightCell`, `crossOut`, `bestResponseArrow`.

Effects vocabulary (Phase 1 subset of the eventual 35): 11 entrances, 2 emphasis,
2 exits. EffectSpec dispatch shape locked.

Resolvers: `anchor` (5 tokens, vertical auto-flip), `size` (5 kinds × 2 formats × 3 roles).

Validation: 4-tier (structural + coords-banned + per-action $ref + semantic incl
anchor + duplicate-id with extractors).

Architecture seams documented in handoff.md for Phase 2.

---

## Phase 1.5 — Visual polish + validator overflow + QA ✓ DONE

Status: **complete**. Addresses quality issues surfaced by the PD scenes;
lays architectural seed for roles+restaging.

Shipped:
- **CalloutBox style system** — 4 styles via `params.style` enum: `neon`
  (default), `card`, `glass`, `bracket`. Auto-contrast text via
  `theme.palette.pick_text_color`. Style dispatch via
  `components/narrative/_callout_styles.py:CalloutStyleSpec`.
  (Note: `bracket` was dropped in Phase 2.0; current shipped set is 3.)
- **Mutation overlay tracking** — `JSONScene._overlays_by_host` + 
  `ActionContext.register_overlay(host_id, mob, overlay_id=...)`. `highlightCell`,
  `crossOut`, `bestResponseArrow` auto-register against host id; `removeComponent`
  fades host + all tracked overlays in one `AnimationGroup`. Optional `id`
  param on mutations exposes overlay as a top-level id in `id_to_mobject`.
  Closes Phase 1 handoff gap #9.
- **Validator overflow detection (always on)** — three new tiers in
  `schema/_dry_run.py`:
  - 4a `check_slot_fits` — component bbox vs slot dims
  - 4c `check_anchor_overflows` — anchored component bbox vs frame bounds
  - 4b `check_collisions` — full dry-run walk, pairwise overlap + frame fit
- **`BaseComponent.measure(params, format)` class method** — pure-math
  estimator returning `(w, h)` without building the mobject. Default reads
  `SIZE_KIND` class attr. Content-driven overrides on TextCard, StatBlock,
  MetricGroup, CalloutBox. The validator and the future layout solver
  share this API.
- **`FRAME_BOUNDS` in `layouts/base.py`** — single source of truth for
  per-format frame dims, consumed by validator + future solver.
- **Auto-contrast palette helper** — `theme.palette.pick_text_color(bg_hex)`
  uses W3C relative luminance.
- **4 QA mega scenes** — `qa_mega_h.json` + `qa_mega_v.json` (component/
  effect/mutation density on `title-body`) and `qa_mega_layouts_h.json` +
  `qa_mega_layouts_v.json` (split/stacked layout edge cases, all anchor
  sides, multi-callout, all styles).
- **PD scene fixes** — `prisoners_dilemma.json` (right-of:pd callout, small
  bar chart) and `prisoners_dilemma_vertical.json` (MetricGroup size=small)
  patched to pass new validator tiers.
- **SIZE_TABLE adjustment** — `large` sizes for matrix/tree/web/default
  now fit `hero` in both formats (were aspirational).

Architectural seams that roles+restaging will reuse verbatim:
- `BaseComponent.measure` (solver's space allocator)
- `_overlays_by_host` (restage pass's overlay cleanup)
- `_dry_run.py` walk shape (solver's pre-flight pass)
- `FRAME_BOUNDS` (frame fit checks)
- `CalloutStyleSpec` (model for future BadgeSpec, ConnectorSpec)

See handoff.md "Phase 1.5 → Phase 2 / roles+restaging" section for
specific extension points.

---

## Phase 2.0 — Visual refinement (PR E1 + E2) ✓ DONE

Status: **complete**. Immediate render bugs surfaced by viewer review
fixed in two passes before the Roles + Restaging architecture starts.

Shipped:
- **PR E1** — `Text.become()` count-up pattern in StatBlock + `_BarValueLabel`
  (eliminates `"0.0"` persistent leak); bar chart value-label floor for
  zero-value bars; first-pass 3-layer neon stack (later superseded); drop
  `bracket` callout style; x-axis title clearance bump.
- **PR E2** — Professional 4-layer neon with `lighten()` helper for
  whitish "hot filament" inner core + subtle interior fill (the visible
  hue + glow effect a real neon sign has); two-rule bar chart label
  positioning (zero-value at fixed floor; non-zero always just above
  bar — consistent across the chart); rewrite of all four QA mega scenes
  as coherent visual demos (not exhaustive parades); Phase 2 brief
  transferred to `handoff.md` for the next agent.

Architectural seams unchanged by Phase 2.0 — the surface Phase 2
(Roles + Restaging) consumes is identical to what Phase 1.5 left.

---

## Phase 2 — Roles + Restaging ✓ DONE

**Status: complete.** All 14 PRs (F through R) shipped. Components have
a *role* at every instant; layouts are *solvers* that allocate space
proportional to roles; every composition change triggers a FLIP-style
restage pass.

Shipped:
- **PR F — Roles schema plumbing.** `role_name` enum + optional `role`
  on every `show_*.json`. `set_role.json` + `actions/set_role.py`.
  `BaseComponent.role` + `DEFAULT_ROLE` (CalloutBox = `annotation`).
  `JSONScene._roles` seeded on every show, dropped on remove.
- **PR G — FLIP restage as no-op.** `_restage(reason)` + `_compute_target_rects`
  on `JSONScene`. Wires the post-show / post-remove / post-set-role hooks.
  Identity planner — no movement yet, but every later PR replaces just
  the planner.
- **PR H — `preferred_size(role)`.** New classmethod on `BaseComponent`
  multiplied by `ROLE_SCALE` (hero 1.5×, primary 1.0×, supporting 0.7×,
  ambient 0.4×, annotation 1.0×, hidden 0×). Linear scaling fits Phase 1
  content; content-driven overrides are opt-in.
- **PR I — Generic flex solver.** Pure-math `flex_solve` in
  `layouts/_flex.py`. Direction + gap + align + proportional shrink +
  `MIN_DIM` floor.
- **PR J — Split layout to solver.** `Layout.solve(cast)` with per-slot
  flex; backward-compat passthrough for 1-member slots keeps PD scenes
  pixel-identical.
- **PR K — Remaining layouts.** Default `Layout.solve` covers hero,
  data-left, data-top, trio, trio-stack, title-body via the per-slot
  flex pattern.
- **PR L — Subject-based callout placement.** `params.subject` on
  CalloutBox + `pick_subject_side` resolver. Solver picks the side based
  on available frame space and layout direction.
- **PR M — Color inheritance from subject.** `inherit_subject_color`
  walks subject refinements (`pd:cell:1,0`, `pd:row:0`) and returns a
  palette key. Explicit `params.color` always wins.
- **PR N — Validator solver-aware composition tier.**
  `check_composition_fit` walks events maintaining cast state, calls
  `layout.solve(cast)` at each step, flags `[composition-fit]` /
  `[composition-overlap]` errors.
- **PR O — `showCalloutSequence`.** Chained one-at-a-time callouts via
  Manim's `Succession`. Schema + action callable + tests.
- **PR P — Three new callout styles.** `neon-bold` (5-layer stack),
  `pull-quote` (no bubble, accent quote marks), `inline-tag` (filled
  chip, no leader). Schema enum updated.
- **PR Q — New QA scenes.** `qa_roles.json`, `qa_roles_v.json`,
  `qa_sequence.json` exercise role transitions + showCalloutSequence.
- **PR R — Documentation sweep.** AGENT.md rules 17/18; plan.md/recap.md/
  handoff.md/_skill.md/README.md updates.

This phase replaces what the original Phase 1 plan called "Phase 2 —
Effects, motion, camera" (camera + remaining effects + asset pipeline).
That original Phase 2 scope moves to **Phase 3** below.

---

## Phase 3 — Effects, motion, camera, hardening

Goal: visual polish + within-scene camera + remaining effect vocabulary +
pipeline survives LLM authoring without supervision. Phase 2's solver
makes restaging continuous; this phase makes the rest of the pipeline
match that quality.

Scope (was original Phase 2 + original Phase 3, merged after Phase 2.0):
- `manim_renderer/effects/` — remaining ~20 effects (entrances 15, emphasis 8, exits 6, transitions 5). Each is a factory function dispatched via dict.
- `cameraZoom` / `cameraPan` / `cameraFocus` actions. `JSONScene` extends `MovingCameraScene`. Camera state interpolates between events. Composes with Phase 2's restage.
- LaggedStart stagger constants wired through component code (no raw floats).
- Map → Manim color handoff audit. Render two test clips back-to-back; verify Morocco's yellow on the map equals Morocco's yellow in a PayoffMatrix label.
- Asset pipeline: `manim_renderer/assets/flags/` populated with SVG country flags. `setup_assets.sh` installs Inter, Barlow Condensed, JetBrains Mono, verifies LaTeX packages.
- Golden frame tests for the top 4 components (PayoffMatrix, BarChart, GameTree, StatBlock). Reference frames in `tests/golden_frames/`. Pixel-diff threshold starts at 2%.
- LLM fuzzing harness: generates 100 valid-schema JSONs from random parameter draws, renders all at `-ql`, flags crashes.
- Preview vs full render modes: `quality: "preview"` → `-ql` (480p, 15fps), `quality: "full"` → `-qh` (1080p, 60fps).
- Escape hatch: `escape_hatch/custom_scenes/` + `runCustomScene` action.

Exit criteria: a Predictive-History-style 90-second video; 50 LLM-authored JSONs render without crashes; schema validation surfaces real authoring errors with useful messages.

---

## Phase 4 — Extended library (ongoing)

Build remaining components from the master list as content demands. Don't pre-build speculatively. Each new component:
1. Inherits BaseComponent
2. Gets registered in `REGISTRY`
3. Gets a schema in `schema/action_schemas/`
4. Gets a unit test
5. Gets a one-line entry in the LLM prompt skill file

Components likely needed in early episodes: FeedbackLoop, EscalationLadder, DecisionTree, SplitComparison, QuoteCard, ChapterCard.

Components defer until requested: Sankey, CoalitionDiagram, RadarChart, SystemDynamicsStock.

---

## Cross-cutting decisions to lock in early

These are decisions cheap now, expensive to change later:

**Manim Community Edition, not ManimGL.** Pin a specific version in requirements.txt. LLMs hallucinate across the two — choose one and constrain prompts to it.

**Component file layout: one component per file.** Keeps git blame clean and lets the LLM read a single file when asked to author a new one.

**JSON action names: `camelCase`, verb-prefixed.** `showPayoffMatrix`, `highlightCell`, `removeComponent`. Matches existing Mapbox actions exactly.

**IDs are kebab-case and human-readable.** `"id": "pd-matrix"`, not `"id": "comp_001"`. Anchor references need readable targets.

**Coordinates never appear in scene JSON.** Hard rule enforced by schema. If a component needs a position, it uses a zone name or an anchor.

**Timing constants only, no raw seconds in component code.** All `run_time` values resolve from `TIMING` dict. Makes global pace adjustments trivial.

**Output goes to `output/manim/<clip_name>.mp4`.** Mirrors `output/<clip_name>.mp4` from the Mapbox pipeline, keeps them separated.

---

## Open questions (deliberately fluid)

- **Should `pipeline/render.py` be a CLI dispatcher or a Python API used by the orchestrator?** Probably both — argparse entry for manual use, importable `render(scene_dict, name)` for n8n/langgraph.
- **Where does `Generation_map.py` belong?** Currently empty. Possibly the orchestrator's scene-generator harness. Leave alone until orchestrator design starts.
- **Audio sync.** Manim has no native audio. Voice-over alignment happens in post (ffmpeg) using timestamps from the JSON timeline. Worth specifying once we know the news-reporter pipeline.
- **Caching.** Re-rendering the same JSON should be free. Hash inputs, cache by hash. Worth doing in Phase 3 if render times become painful.
- **Multi-scene composition.** Currently each JSON = one clip. Long-form videos = N JSONs concatenated by orchestrator. Could move concatenation into the pipeline; probably shouldn't.
- **Should layouts be Python classes or JSON files?** JSON is more uniform with the rest of the system. Python is easier to debug. Start with Python, expose as data if it stabilizes.

---

## What we're not building (yet)

- A scene editor / GUI. JSON is the interface; the LLM is the author.
- Live-preview / hot reload. Render is batch.
- Cross-clip transitions inside Manim. Those happen in ffmpeg/post.
- Templates above the component layer. Pure timeline+slots system first; if patterns emerge across many videos, lift them into templates in Phase 4.


---

## Round 1–4 deltas (post-Phase 2)

Four iterative fix passes after the original Phase 2 Roles+Restaging
brief landed. Each addressed user-reported visual issues that surfaced
once the system was rendering real content. Cumulative effect:

- **Round 1 (responsive core):** removed the lone-primary passthrough,
  added scale animation in `_restage`, brought subject callouts into
  the solver cast, added `setLayout` action.
- **Round 2 (visual fixes):** restored lone-primary passthrough behind
  a sentinel rect; reposition hook so callout leaders re-anchor after
  restage; setLayout pins slots-block ids instead of migrating them;
  `GEOPOAI_DEBUG=1` trace + `debug_replay.py` Manim-free dry-run.
- **Round 3 (overlay visibility):** auto-bind overlay events to the
  layout's PRIMARY_SLOT; unify anchor + subject callouts (same
  reflow + color + leader behavior); cap restage scale at 1.0 so
  mobjects never grow beyond build size; `pick_subject_side` stays
  in axis.
- **Round 4 (root-cause sweep):** position-only sentinel for lone
  primary (no scale at all, stops title shrinking); mutation overlay
  rebuild recipes (Transform-based smooth follow); full-frame reflow
  when only one slot is occupied; color inheritance via
  `palette_color` attribute; showCalloutSequence cleanup registers
  inner callouts as host overlays; PD vertical rewritten to use the
  stacked layout (matrix on top, bar chart on bottom, callouts
  flipping between them).

The placement model is documented in detail in `AGENT.md` under
"Current placement model". Decision rationale lives in `recap.md`
§22d.

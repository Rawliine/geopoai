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
- `manim_renderer/theme/` — palette, typography, timing, easing. Palette must be diffed against `renderer/effects.css` actor colors. Same hex codes everywhere.
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

## Phase 2 — Effects, motion, camera (≈1 week)

Goal: visual polish + within-scene camera, full effect vocabulary.

- `manim_renderer/effects/` — entrances (15), emphasis (8), exits (6), transitions (5). Each is a factory function: `entrance(mobject, effect_name, timing) -> Animation`. Defined as data, dispatched via dict — not a switch statement.
- Easing + timing constants enforced. No raw `run_time` floats in component code; everything reads from `TIMING`.
- `cameraZoom` / `cameraPan` / `cameraFocus` actions on the timeline. `JSONScene` already extends `MovingCameraScene`. Camera state interpolates between timeline events.
- LaggedStart stagger constants (`dense=0.08`, `normal=0.15`, `dramatic=0.3`) wired in.
- Audit the map → Manim color handoff. Render two test clips back-to-back; verify Morocco's yellow on the map equals Morocco's yellow in a PayoffMatrix label.
- Asset pipeline: `manim_renderer/assets/flags/` populated with SVG country flags (flagcdn or bundled set). `setup_assets.sh` installs Inter, Barlow Condensed, JetBrains Mono on the render machine and verifies LaTeX packages.

Exit criteria: a Predictive-History-style 90-second video that doesn't feel like two different tools were glued together.

---

## Phase 3 — Validation & hardening (≈1 week)

Goal: pipeline survives LLM authoring without supervision.

- Full JSON schema coverage. Every action has a `schema/action_schemas/<action>.json`. Validation rejects unknown actions, missing params, wrong types.
- Schema includes semantic checks: `at` values within `duration`, `id` references resolve to declared components, `anchor:id` targets exist.
- Component unit tests: each component has `tests/components/test_<name>.py` that renders it at `-ql` with sample params. CI runs all on every commit.
- Golden frame tests for the top 4 components (PayoffMatrix, BarChart, GameTree, StatBlock). Reference frames checked into `tests/golden_frames/`. Pixel-diff threshold: TBD, start at 2%.
- LLM fuzzing harness: generates 100 valid-schema JSONs from random parameter draws, renders all at `-ql`, flags crashes and obviously-broken outputs.
- Preview vs full render modes: `quality: "preview"` → `-ql` (480p, 15fps), `quality: "full"` → `-qh` (1080p, 60fps). Orchestrator defaults to preview, escalates to full on approval.
- Escape hatch: `escape_hatch/custom_scenes/` directory + `runCustomScene` action. Hand-authored Manim scenes registered by name. Documented in AGENT.md.

Exit criteria: 50 LLM-authored JSONs render without crashes. Schema validation surfaces real authoring errors with useful messages.

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

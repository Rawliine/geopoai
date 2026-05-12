# recap.md — Design decisions, reasoning, open questions

This document captures the full design discussion behind the Manim layer of GeoPoAI. It is more discursive than `AGENT.md` and longer than `plan.md`. When a decision later looks weird, the *why* lives here. Mark sections as `[FLUID]` if revisiting them is cheap; `[LOCKED]` if changing them late would cascade.

---

## 1. Vision

**Content type:** automated geopolitical analysis and game-theory explainers, in the editorial voice of "Predictive History" (Prof Jiang). Clean, restrained visuals, information-dense, deliberately paced. Dark backgrounds, high-contrast typography, motion that means something.

**Format split:**
- Long-form (1+ minute) → horizontal 16:9
- Short-form → vertical 9:16

**Retention target:** ≥50% watch time on 1-minute-plus videos. The visual layer is the lever — narration alone won't hold attention; visuals that arrive on cue with the script will.

**Automation goal:** an LLM agent (n8n or langgraph orchestration) authors scene JSON; the rendering pipeline produces clips; a final composition step assembles them with B-roll, news-reporter footage, and audio.

---

## 2. Architecture at a glance

Two rendering engines, one orchestrator on top.

```
                      ORCHESTRATOR (n8n / langgraph)
                      ├── script generation
                      ├── scene JSON generation (per beat)
                      ├── dispatch render jobs
                      └── final composition (ffmpeg)
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
       MAPBOX ENGINE (done)              MANIM ENGINE (to build)
       country fills, borders,           payoff matrices, game trees,
       arrows on geography               charts, system diagrams
                │                                │
                └────────────┬───────────────────┘
                             ▼
                       MP4 clip output
```

**Why two engines, not one:** the map work is inherently geographic — pan across continents, fill territories, draw arrows between cities. Manim cannot do that well. The diagrammatic work is inherently abstract — payoff matrices, decision trees, equations. A browser-based renderer would handle some of it but Manim's strength is exactly this. Different tools for different jobs; visual cohesion comes from a shared theme system, not a shared renderer.

`[LOCKED]` — two engines.

---

## 3. The fork we considered: Manim vs SVG/D3

For game-theory and abstract diagrams, two real options:

- **Manim**: Python, animation-first, math-native, slower iteration, distinctive aesthetic
- **SVG + D3 in browser**: same Playwright pipeline as map engine, faster iteration, more flexible, but no built-in animation primitives

We chose Manim because:
- The math-native bits (equation morphing, expected utility derivations) are first-class
- The aesthetic is a known quantity — Predictive-History-style content visibly leans on Manim conventions
- A second pipeline adds operational cost but cleaner mental separation
- We have control over the constraint surface — by limiting LLM output to a JSON DSL, we get Manim's expressiveness without exposing its API

`[FLUID]` — if Manim's render times or LaTeX brittleness become unbearable, falling back to SVG-in-Playwright for a subset of components is on the table. The component interface is abstract enough that swapping the renderer for one type of component is a Phase 5 concern, not a rewrite.

---

## 4. Authoring model: templates vs components vs direct code

Four options were on the table:

1. **Pure templates** — LLM picks a preset scene type, fills slots. Safe, limited.
2. **Pure components + timeline** — LLM composes freely from primitives on a timeline. Same shape as our Mapbox JSON. Flexible, more surface area for errors.
3. **LLM writes Python** — maximum freedom, maximum hallucinations. Rejected.
4. **Layered** — templates on top, components underneath, escape hatch for the 5% case.

We chose **layered**, but starting with the component layer. Templates can be lifted out later when patterns emerge across many videos.

**Reasoning:** the LLM is already trained on our Mapbox JSON shape. Reusing the timeline-of-events structure means it transfers existing patterns. Templates added prematurely lock us into compositions we haven't validated. Going component-first is slightly riskier for early videos but compounds better.

`[FLUID]` — re-evaluate after 10 videos. If three of them used the same component arrangement, lift it to a template.

---

## 5. JSON shape

Same general shape as the Mapbox JSON, with three top-level extensions: `format`, `scene.layout`, and a `slots` / `overlays` split.

```json
{
  "renderer": "manim",
  "format": "horizontal",
  "quality": "preview",
  "scene": {
    "layout": "split",
    "duration": 12,
    "theme": "dark"
  },
  "slots": {
    "left":  { "at": 0.0, "action": "showGameTree",  "params": { "id": "tree-1" } },
    "right": { "at": 0.0, "action": "showBarChart",  "params": { "id": "chart-1" } }
  },
  "overlays": [
    { "at": 3.0, "action": "showLabel",     "params": { "id": "callout", "anchor": "below:tree-1", "text": "Backward induction" } },
    { "at": 5.0, "action": "highlightCell", "params": { "target": "chart-1", "index": 2 } }
  ],
  "timeline": [
    { "at": 8.0, "action": "cameraFocus", "params": { "target": "tree-1" } }
  ]
}
```

The split between `slots`, `overlays`, and `timeline` is deliberate:
- **`slots`** — the primary content. One per named slot in the layout. Anchors the composition.
- **`overlays`** — annotations, callouts, highlights. Layer above slots. Use relative anchors only.
- **`timeline`** — events that don't fit either category (camera moves, scene-level effects, custom scenes).

The Mapbox JSON used `timeline` for everything. Manim scenes are more compositional, less geographic, so splitting reduces LLM confusion about where to place each event.

`[FLUID]` — if the split feels unnatural after 5 episodes, collapse back to a single `timeline` array.

---

## 6. Positioning system

**Core rule: coordinates never appear in LLM-authored JSON.**

Three positioning mechanisms layered together:

### Layer 1 — Layout templates
The LLM picks a named layout. Each layout has hardcoded slot definitions in unit space. Slots are referenced by name only.

### Layer 2 — Named zones (within `runCustomScene` or rare cases)
A 3×3 grid of zone names: `TOP-LEFT`, `TOP-CENTER`, `TOP-RIGHT`, `MID-LEFT`, `CENTER`, `MID-RIGHT`, `BOT-LEFT`, `BOT-CENTER`, `BOT-RIGHT`. Used only when layout slots aren't enough.

### Layer 3 — Relative anchors
Overlays and labels position themselves relative to component IDs: `"anchor": "below:tree-1"`. The renderer builds a dependency graph and resolves positions after components are measured.

Anchor vocabulary: `above:id`, `below:id`, `left-of:id`, `right-of:id`, `inside:id`, `next-to:id`.

In vertical format, `right-of` and `left-of` auto-map to `below` and `above` (with optional opt-out). This is the single most error-prone area; the resolver layer absorbs it so components and JSON authors stay format-agnostic.

`[LOCKED]` — no coordinates in JSON, ever. This is the cleanest contract we can give the LLM.

---

## 7. Format system — horizontal and vertical

A single `format` flag in the JSON drives the entire downstream stack:

| Layer | What changes |
|---|---|
| Manim config | Frame dimensions: 14.2×8.0 vs 8.0×14.2 |
| Layouts | Different library — horizontal `split` ≠ vertical `split` (becomes `stacked`) |
| Component sizes | `small/medium/large` resolve to different unit values per format |
| Typography | Vertical needs ~30% larger fonts (mobile, arm's length) |
| Anchors | `right-of` auto-maps to `below` in vertical |
| Some components | `HorizontalTimeline` swaps for `VerticalTimeline` entirely |
| Animation choreography | Reveal left→right (horizontal) vs top→bottom (vertical) |

The format string passes through all resolvers. Components themselves stay format-agnostic — they receive resolved coordinates and sizes.

**Key implication:** every layout has either a vertical twin or a documented "horizontal only" marker. The schema enforces format/layout compatibility.

`[LOCKED]` — format as first-class JSON field, format-aware resolvers, format-agnostic components.

---

## 8. Component library plan

**Master list, by category** (the full list lives in `plan.md` Phase 4; this is the canonical taxonomy):

- **Game Theory** — PayoffMatrix, ExtensiveFormTree, StrategyElimination, NashArrows, MixedStrategyDiagram, RepeatedGameTimeline, CoalitionDiagram
- **Decision & Systems** — DecisionTree, FlowChart, CausalDiagram, FeedbackLoop, SystemDynamicsStock, EscalationLadder
- **Data Viz** — BarChart, LineChart, AreaChart, ScatterPlot, BubbleChart, RadarChart, SankeyDiagram, TreemapBlock, HeatmapGrid, DonutChart
- **Timeline & Historical** — HorizontalTimeline, VerticalTimeline, DualTimeline, GanttBar, CountdownClock
- **Geopolitical Relations** — AllianceWeb, PowerTransitionCurve, InfluenceZoneVenn, DependencyMatrix, ThreatPerceptionDiagram, NegotiationSpace
- **Economic & Resource** — SupplyDemandCurves, ProductionPossibilityFrontier, DebtClockBar, TradeFlowArrows, SanctionsImpactPanel
- **Military & Conflict** — OrderOfBattleTree, AttritionCurve, LossExchangeRatio, NuclearTriad, EscalationMatrix
- **Institutional & Political** — VetoPlayerDiagram, PoliticalSpectrum, ElectoralCoalitionSankey, ConstitutionalFlowchart, InternationalInstitutionMap
- **Narrative & Presentation** — SplitComparison, ThreeScenarioFan, StatBlock, QuoteCard, ChapterCard, AnnotatedImage, ComparisonTable

~55 components total. **Build order is content-driven** — Phase 1 builds the 8 highest-ROI; everything else is on demand. Pre-building is the enemy.

`[FLUID]` — taxonomy may shift as we discover overlaps. CausalDiagram and FlowChart may merge. AllianceWeb and InfluenceZoneVenn may share a base class.

---

## 9. Map → Manim handoff points

The viewer should never feel they've switched apps. Natural cuts:

| Map establishes | Manim picks up |
|---|---|
| Country borders light up | AllianceWeb or DependencyMatrix explains *why* |
| Arrow from A → B | TradeFlowArrows or SanctionsImpactPanel shows the *numbers* |
| Territory fill changes | AttritionCurve or LossExchangeRatio shows the *cost* |
| City pulse rings | OrderOfBattle or EscalationLadder shows *what's happening* |
| Zoom to region | PowerTransitionCurve or InfluenceZoneVenn gives *structural context* |

**Techniques for cohesion:**
- Color continuity — actor colors identical across both engines. Morocco's yellow on the map is Morocco's yellow in Manim, same hex.
- Motion direction continuity — end-of-map pan direction matches start-of-Manim reveal direction.
- Shape echo — closing element of the map clip (pulse, glow) opens the Manim clip's first reveal.
- Shared visual elements — flag colors in `PlayerLabel` match the highlighted region on the map.

`[LOCKED]` — color palette synced across `renderer/effects.css` and `manim_renderer/theme/palette.py`. CI enforces equality.

---

## 10. Effects vocabulary

**35 effect names, frozen.** Closed vocabulary the LLM picks from.

```
Entrances:    write-in | grow-up | grow-down | fade-in | slam |
              slide-left | slide-right | slide-up | slide-down |
              draw-out | count-up | typewriter | level-by-level |
              stagger-in | spiral-in

Emphasis:     pulse | highlight | strike | glow | shake |
              surround | color-shift | dim-others

Exits:        fade-out | shrink | slide-out-left | slide-out-right |
              dissolve | grey-out

Transitions:  fade | wipe-left | wipe-right | zoom-in | zoom-out
```

**Mapping to Manim primitives** is dispatched via `effects/<category>.py` — each effect name resolves to a factory that returns an `Animation`. Components don't know about Manim's animation classes directly; they ask for an effect by name.

Per-scene restraint rule (in the system prompt, not enforced by schema): **no more than 3 emphasis effects in one scene.** Variety reads as amateurish.

`[FLUID]` — vocabulary may grow by 1–2 names per quarter as new content needs emerge. Removing names is harder; do not add speculatively.

---

## 11. Motion design principles

Three rules, enforced by code reviews and by sensible defaults in the easing/timing system.

**1. Reveal, don't appear.** Nothing pops in. Default to `fade-in` minimum; ideally a contextual entrance (write-in for borders, count-up for stats, level-by-level for trees).

**2. Attention is directed, not scattered.** At any single frame, one element is the focal point. Effects that fight for attention are noise. The scene runner doesn't enforce this — it's an authoring principle.

**3. Motion has meaning.** Drawing arrow = causation. Spreading fill = territory/growth. Crossout = elimination. Pulse = activity. Glow = optimality. The semantic map between effect and meaning is consistent across the library.

**Easing:**
- Enters use `ease_out_cubic` (confident arrival)
- Exits use `ease_in_cubic` (clean departure)
- Transforms use `ease_in_out_cubic` (smooth both ends)
- `linear` reserved for data lines and progress bars
- `ease_out_back` (slight overshoot) used sparingly for impact
- `ease_out_elastic` (spring) used almost never

**Timing:** 7 named slots (`instant`, `snap`, `fast`, `normal`, `slow`, `dramatic`, `crawl`) covering 0.0s–3.0s. LLM picks names; component code reads from `TIMING` dict; raw floats are banned in component code.

**Hold times matter more than animation speed.** Amateur Manim animates too fast and holds too short. A reveal that takes 0.6s should hold for 1.5–2s after.

`[LOCKED]` — easing palette, timing scale, three principles.

---

## 12. Color & typography systems

### Palette (`manim_renderer/theme/palette.py`, mirrors `renderer/effects.css`)

```
actors:
  actor_a #3498db (blue),   actor_b #e74c3c (red),
  actor_c #2ecc71 (green),  actor_d #f39c12 (orange),
  actor_e #9b59b6 (purple)

semantic:
  positive #2ecc71, negative #e74c3c, neutral #95a5a6,
  highlight #f1c40f, contested #e67e22

ui:
  background #0e1116, surface #1a1f2e, border #2c3e50,
  text_primary #ecf0f1, text_secondary #95a5a6, text_accent #f1c40f
```

**One color accent per scene.** Background near-black, text near-white, one accent dominating. A second accent appearing means a second actor has entered.

### Typography

```
primary  → Inter             (labels, body, numbers)
display  → Barlow Condensed  (titles, chapter cards)
mono     → JetBrains Mono    (codes, coordinates)
math     → STIX Two Math     (LaTeX fallback)
```

Never more than 2 fonts in a scene. **Never use Manim's default LaTeX-for-everything style** — looks academic, not editorial.

Font sizes scale with format (vertical ~30% larger). Defined as `FONT_SCALE[format][role]` in `theme/typography.py`.

`[LOCKED]` — palette, font choices. Specific size values may tune.

---

## 13. Camera

`JSONScene` extends `MovingCameraScene`. Three timeline actions:

```
cameraZoom   — change zoom level
cameraPan    — move center to a coordinate or anchor
cameraFocus  — frame a specific component with padding
```

Camera interpolates between events using `EASE["emphasis"]`. The default frame is fully reset between scenes (each JSON = one clip = one scene).

**Use sparingly.** Camera moves on top of element animation is overload. Either the camera moves OR elements animate; rarely both.

`[FLUID]` — camera vocabulary may expand. `cameraOrbit` and `cameraShake` are candidates.

---

## 14. Asset management

**Fonts** — installed by `manim_renderer/assets/setup_assets.sh` on the render machine. CI verifies they're available before tests run. Missing fonts = silent fallback to defaults = visual regression.

**Country flags** — SVG set in `manim_renderer/assets/flags/`. Source: flagcdn.com or a bundled CC0 set. Loaded by `FlagBadge`/`PlayerLabel` via `SVGMobject`.

**Icons** — `manim_renderer/assets/icons/` for non-flag SVGs (military symbols, currency symbols, etc). Used by components that need them; not loaded eagerly.

**LaTeX packages** — `setup_assets.sh` installs the packages our `MathTex` usage needs (`amsmath`, `amssymb`, `mathtools`). Manim's LaTeX dependency is the most common production failure point — explicitly verify in CI.

**Containerization** — if/when we Dockerize, the Dockerfile installs fonts + LaTeX explicitly. Don't rely on the base image.

`[FLUID]` — flag source may change. Icons inventory grows by demand.

---

## 15. JSON schema validation

Three-tier validation, all running before any render:

1. **Structural** — does the JSON match `scene_schema.json`? (top-level fields, required props, types)
2. **Action-level** — does each action's `params` match `action_schemas/<action>.json`? (per-component param schemas)
3. **Semantic** — anchor IDs resolve, `at` values within `duration`, layout/format compatible, no duplicate IDs

Errors include JSON path + human-readable explanation. The LLM authoring loop reads these to self-correct (this is the agent's tightest feedback loop in the pipeline — fast, deterministic, no rendering required).

`[LOCKED]` — schema-first authoring. The schema is the contract between the LLM and the renderer.

---

## 16. Testing strategy

Three layers:

**Component unit tests** — each component has `tests/components/test_<name>.py` that renders it at `-ql` with representative params. CI runs all of them on every commit. Catches breakage when a base class or theme value changes.

**Golden frame tests** — top components have reference frames in `tests/golden_frames/`. Each build re-renders and pixel-diffs. Threshold tuned per component (text-heavy ones tolerate more drift than geometric ones).

**LLM output fuzzing** — `tests/fuzz/` generates 100 schema-valid JSONs with randomized parameters, renders all at `-ql`, flags crashes and obvious failures (empty frames, overlapping text, out-of-bounds elements). Non-blocking but reviewed weekly.

`[FLUID]` — diff thresholds, fuzz draw distributions. The structure stays.

---

## 17. Quality modes & preview discipline

```
preview → -ql  (480p, 15fps)   — default for LLM-generated content
draft   → -qm  (720p, 30fps)   — intermediate review
full    → -qh  (1080p, 60fps)  — final renders only
```

LLM-authored JSONs default to `preview`. The orchestrator escalates to `full` only after approval (human review, or automated heuristic — a confidence threshold from script-to-visual alignment scoring, TBD).

This matters because Manim render times at full quality compound fast. A 30-second clip at 1080p60 can take 2+ minutes; at preview it's seconds.

`[LOCKED]` — three-mode system. Specific render flags may tune.

---

## 18. Escape hatch — custom scenes

For the ~5% of scenes where templates + components don't compose. Hand-authored Manim scenes living in `manim_renderer/escape_hatch/custom_scenes/<name>.py`, registered in `escape_hatch/__init__.py`, invoked from JSON:

```json
{ "action": "runCustomScene", "params": { "name": "operation_anaconda", "duration": 8 } }
```

Custom scenes:
- Receive `params: dict, theme: Theme, format: str` like components
- Must respect palette and timing constants
- Bypass the layout system
- Are code-reviewed; **LLM does not author these**

This is the pressure relief valve. Without it, edge cases force the component library to grow beyond what's maintainable.

`[LOCKED]` — escape hatch exists. Specific custom scenes are content-driven.

---

## 19. Orchestration layer (out of scope for this doc)

This doc is about the rendering layer. The orchestrator (n8n / langgraph) sits above and is its own design problem. Brief notes for context:

- The orchestrator generates scene JSON, dispatches renders, collects clips, composes the final video
- Final composition is ffmpeg-based: clip concatenation + B-roll overlay + audio mix
- News-reporter footage and B-roll are layered in post, not inside the render engines
- Cross-clip transitions (fades, wipes) happen in ffmpeg, not Manim

The render engines do not know about the orchestrator. They take a JSON in, produce an MP4 out. Stateless.

`[FLUID]` — orchestrator choice (n8n vs langgraph) doesn't affect anything in this doc.

---

## 20. Things deliberately unresolved

Areas where the right answer will emerge from doing the work:

- **Audio sync.** Voice-over timing alignment. Currently assumed to happen in post via timestamps from the JSON timeline. May need a sync field added to actions if drift becomes an issue.
- **Caching.** Re-rendering the same JSON should be free. Hash inputs, cache by hash. Worth doing if render volume grows.
- **Multi-scene composition inside the renderer.** Each JSON is one clip today. May want to support multi-clip JSONs if certain narrative beats always go together.
- **`Generation_map.py`** — currently empty. Possibly the orchestrator's scene generator. Leave alone until orchestrator design begins.
- **Component versioning.** When PayoffMatrix v2 is incompatible with v1, how do old JSONs render? Probably via a `version` field on the action. Defer until it's a real problem.
- **Localization.** Non-English script support. Manim's `MarkupText` handles unicode but right-to-left layouts may need component-level changes. Deferred.

---

## 21. What this design is consciously *not* optimizing for

- **Hand-authoring ergonomics.** JSON-by-hand is annoying. The system is designed for LLM authoring with human review, not human authoring.
- **Real-time preview.** Manim renders are batch. Iteration time is render time. Preview mode (`-ql`) is the response to this, not a live preview.
- **Render speed.** Visual quality + LLM authoring reliability are the priorities. Render-time optimization (caching, parallelism) is a Phase 5 concern.
- **Generality.** The component library serves geopolitical / game-theory content specifically. A `ChemistryReaction` component is not in scope and isn't a mistake to omit.

---

## 22. Decision log

A compact list of what we decided and where the reasoning lives in this doc.

| Decision | Section | Status |
|---|---|---|
| Two rendering engines, separate | §2 | LOCKED |
| Manim Community Edition | §3 | LOCKED |
| Layered authoring (component-first) | §4 | FLUID |
| JSON shape: slots/overlays/timeline | §5 | FLUID |
| Coordinates banned in JSON | §6 | LOCKED |
| Three positioning layers (layouts/zones/anchors) | §6 | LOCKED |
| Format as first-class flag | §7 | LOCKED |
| Component library by category, ~55 total | §8 | FLUID |
| Color palette synced across engines | §9 | LOCKED |
| 35-effect closed vocabulary | §10 | FLUID (rarely additive) |
| Motion principles + easing/timing constants | §11 | LOCKED |
| Color + typography system | §12 | LOCKED |
| Camera = MovingCameraScene + 3 actions | §13 | FLUID |
| Asset pipeline (fonts/flags/LaTeX) | §14 | FLUID |
| Three-tier schema validation | §15 | LOCKED |
| Three-layer test strategy | §16 | FLUID |
| Three quality modes, preview default | §17 | LOCKED |
| Escape hatch for custom scenes | §18 | LOCKED |

`LOCKED` = changing it late forces cascading rewrites. `FLUID` = revisit on signal.

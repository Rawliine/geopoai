# AGENT.md — GeoPoAI

Read this first. This file is the working brief for any agent (Claude Code, automated PRs, future-you-at-3am) editing this repo.

---

## What this project is

A pipeline that converts scene JSON into MP4 video clips for short-form geopolitical / game-theory content. Two rendering engines live side by side:

- **Mapbox engine** (existing, complete) — Mapbox GL JS in a headless Chromium, driven by Playwright. Renders maps, country fills, borders, arrows, ripples. Entry: `pipeline/render_scene.py`.
- **Manim engine** (in progress) — Manim Community Edition. Renders payoff matrices, game trees, charts, system diagrams. Entry: `pipeline/render_manim.py`.

Both consume JSON of the same general shape (`duration`, `timeline`, action-based events). An LLM authors the JSON. The two engines stay separate but their visual languages (colors, typography, motion) are designed to feel like one piece.

---

## Repository layout

```
GeoPoAI/
├── pipeline/
│   ├── render.py              # unified dispatcher (reads "renderer" field)
│   ├── render_scene.py        # Mapbox engine entry (existing, do not break)
│   └── render_manim.py        # Manim engine entry
│
├── renderer/                   # Mapbox/Playwright engine
│   ├── map.html
│   ├── effects.js
│   └── effects.css
│
├── manim_renderer/             # Manim engine
│   ├── scene.py                # JSONScene(MovingCameraScene) — the runner
│   ├── registry.py             # action → component class map
│   ├── theme/
│   │   ├── palette.py          # colors — MUST match renderer/effects.css
│   │   ├── typography.py       # fonts + sizes per format
│   │   ├── timing.py           # TIMING constants
│   │   └── easing.py           # EASE dict, rate funcs
│   ├── layouts/
│   │   ├── base.py
│   │   ├── horizontal.py       # 16:9 layouts
│   │   ├── vertical.py         # 9:16 layouts
│   │   └── resolver.py         # picks layout, resolves slot → coords
│   ├── components/
│   │   ├── base.py             # BaseComponent(VGroup)
│   │   ├── game_theory/
│   │   ├── data_viz/
│   │   ├── systems/
│   │   ├── narrative/
│   │   └── geopolitical/
│   ├── effects/
│   │   ├── entrances.py
│   │   ├── emphasis.py
│   │   ├── exits.py
│   │   └── transitions.py
│   ├── resolvers/
│   │   ├── anchor.py           # below:id → coord (format-aware)
│   │   ├── size.py             # small/medium/large → unit dims per format
│   │   └── camera.py
│   ├── schema/
│   │   ├── scene_schema.json
│   │   ├── validator.py
│   │   └── action_schemas/<action>.json
│   ├── escape_hatch/
│   │   └── custom_scenes/      # hand-authored, registered by name
│   ├── assets/
│   │   ├── fonts/
│   │   ├── flags/              # SVG country flags
│   │   └── icons/
│   └── tests/
│       ├── components/         # one test per component
│       ├── golden_frames/      # reference images for diff testing
│       └── fuzz/               # LLM output fuzzer
│
├── config/                     # data prep for the map engine (existing)
├── scripts/
│   ├── map/                    # Mapbox scene JSONs
│   └── manim/                  # Manim scene JSONs
├── data/                       # cached GeoJSON
├── output/
│   ├── (Mapbox MP4s here)
│   └── manim/                  # Manim MP4s here
└── requirements.txt
```

---

## Hard rules

These are not style preferences. Breaking them breaks the pipeline.

1. **Coordinates never appear in scene JSON.** Use zone names (`"CENTER"`, `"TOP-RIGHT"`) or anchors (`"below:matrix-1"`). Schema rejects raw `x`/`y` values. The renderer is the only place coordinates exist.

2. **Colors are pulled from `theme/palette.py`, never hardcoded.** If you write `"#3498db"` in component code, you are wrong. The same hex must work on both the map and Manim — `palette.py` and `effects.css` are diffed in CI.

3. **Timings are pulled from `theme/timing.py`, never raw floats in component code.** `TIMING["normal"]` not `0.6`.

4. **One component per file.** `payoff_matrix.py` defines exactly one component. Helpers go in private functions inside the same file unless they're reused.

5. **Every new component:** inherits `BaseComponent`, registers in `COMPONENT_REGISTRY`, gets a schema in `schema/action_schemas/`, gets a test in `tests/components/`, and gets an entry in `scripts/manim/_skill.md`. No exceptions. The LLM authoring layer relies on schema coverage being complete.

6. **Manim Community Edition only.** No ManimGL imports. Pinned in `requirements.txt`.

7. **Format-awareness is mandatory.** Every component must render correctly in both horizontal (`16:9`, 1920×1080) and vertical (`9:16`, 1080×1920). Use the `format` flag passed at init. Components stay format-agnostic; resolvers (`resolve_size`, `resolve_anchor`) absorb format differences.

8. **Do not modify the Mapbox engine** (`renderer/`, `pipeline/render_scene.py`, `config/`) while building Manim. It is complete and shipping. Touch it only for the shared dispatcher and for color-palette synchronization.

9. **Anchor coords sample at call time.** When an anchored event fires, `resolve_anchor` reads the target's *current* state — not its post-animation state. If the target is mid-animation, the anchor sees the in-flight position. Don't anchor against actively-moving targets.

10. **Two registries, two dispatch paths.** `COMPONENT_REGISTRY` instantiates new mobjects (the `showXxx` family). `ACTION_REGISTRY` mutates or removes existing ones (the `removeComponent`, `highlight*`, `crossOut`, future `cameraXxx` family). Mutations never instantiate; they take an `ActionContext` and return `Animation | None`. Don't bury mutation logic inside a component class.

11. **Effects are EffectSpecs, not free-form callables.** Adding an entrance/emphasis/exit means appending an `EffectSpec(name, factory, required, optional)` to the relevant module's dict and adding the name to `scene_schema.json`'s effect enum. The `required`/`optional` fields drive schema generation and `_skill.md` autogen — `**kwargs`-only factories don't scale to 35 effects.

---

## The data flow, in detail

```
scene.json
    │
    ▼
pipeline/render.py
    │  reads "renderer" field
    ├── "mapbox"  → pipeline/render_scene.py  → existing Playwright flow
    └── "manim"   → pipeline/render_manim.py
                       │
                       ▼
                manim_renderer/schema/validator.py
                       │  validates against scene_schema.json
                       │  + per-action schemas
                       ▼
                manim_renderer/scene.py
                  JSONScene(MovingCameraScene)
                       │
                       ├── construct():
                       │     ├── resolve layout (manim_renderer/layouts/)
                       │     ├── sort timeline by "at"
                       │     ├── for each event:
                       │     │     ├── lookup action in REGISTRY
                       │     │     ├── instantiate/lookup component
                       │     │     ├── resolve anchors + sizes
                       │     │     ├── pick entrance effect from effects/
                       │     │     └── self.play(animation, run_time=TIMING[...])
                       │     └── wait for inter-event gaps
                       │
                       ▼
                Manim renders frames → MP4
                       │
                       ▼
                output/manim/<clip_name>.mp4
```

---

## How to add a new component

1. Pick a category subdir (`game_theory`, `data_viz`, `systems`, `narrative`, `geopolitical`).
2. Create `<snake_case_name>.py`.
3. Subclass `BaseComponent`. Implement `build()`. Override `entrance(effect, timing, **extra)` and `exit(effect, timing, **extra)` ONLY for bespoke behavior — the base class already dispatches to `effects.entrances.get_entrance` / `effects.exits.get_exit`. Add `_get_anchor_<token>(arg)` methods for any custom anchors (the standard 9 — `top`/`bottom`/`left`/`right`/`center`/4 corners — come from the base).
4. Read sizes from `theme.typography` and `resolvers.size` — never hardcode pixel or unit values. If your component takes a `size` param, the runner passes resolved dims as `params["_resolved_size"]`.
5. Register in `manim_renderer/registry.py:COMPONENT_REGISTRY`: `"showFooBar": FooBar`.
6. Create `manim_renderer/schema/action_schemas/show_foo_bar.json` with full param schema. Use `$ref` into `scene_schema.json#/definitions/` for `id_string`, `timing_name`, `anchor_string`, `size_role`, `color_key`, `entrance_effect`, etc. Set `additionalProperties: false`.
7. Create `manim_renderer/tests/components/test_foo_bar.py` — render both formats at `-ql`. Add unit tests for any non-trivial logic (no rendering required).
8. Add a section to `scripts/manim/_skill.md` describing the action — required params, accepted effects, one minimal JSON example.

The schema is the contract. If it's not in the schema, the LLM doesn't know about it and won't generate it.

---

## How to add a new layout

1. Decide if it's horizontal-native or has a vertical twin.
2. Add to `manim_renderer/layouts/horizontal.py` and/or `vertical.py` as a dataclass with named slots and their unit-space rects.
3. Slot names should be reusable across layouts: `left`, `right`, `top`, `bottom`, `main`, `inset`, `A`, `B`, `C`, `D`.
4. Update `layouts/resolver.py` if new resolution logic is needed (usually not).
5. Add the layout name to the `scene_schema.json` enum.

---

## How to add an effect

Effects are factory functions wrapped in `EffectSpec`: `(mobject, *, run_time, **params) -> Animation`.

1. Pick the right module (`entrances`, `emphasis`, `exits`, `transitions`).
2. Add the function. Use only `rate_func` values from `theme.easing.EASE`. Required params are listed in the `EffectSpec`'s `required` tuple; defaults go in `optional`.
3. Register in the module's dict (`ENTRANCES`, `EMPHASIS`, `EXITS`) as an `EffectSpec(name, factory, required, optional)`.
4. Add the effect name to the matching enum in `scene_schema.json#/definitions/` (`entrance_effect`, `emphasis_effect`, `exit_effect`).

Effect names are global. Two components can use `"write-in"` and it must mean the same thing visually.

---

## Quality modes

```
quality: "preview"  → -ql  (480p, 15fps, fast iteration)
quality: "full"     → -qh  (1080p, 60fps, final)
quality: "draft"    → -qm  (720p, 30fps, intermediate)
```

LLM-generated scenes default to `preview`. Human or approved scenes use `full`. Schema validates the enum.

---

## Camera

`JSONScene` extends `MovingCameraScene`. Three new timeline actions:

```json
{ "action": "cameraZoom",  "params": { "factor": 0.6, "duration": "normal" } }
{ "action": "cameraPan",   "params": { "to": "below:tree-1", "duration": "slow" } }
{ "action": "cameraFocus", "params": { "target": "matrix-1", "padding": 0.3 } }
```

Camera state interpolates between events using `EASE["emphasis"]`. Camera resets to default at scene end unless `keep` is true.

---

## Escape hatch — custom scenes

For the ~5% of scenes where no template fits:

1. Hand-author a Manim scene in `manim_renderer/escape_hatch/custom_scenes/<name>.py`.
2. It must accept `params: dict, theme: Theme, format: str` like a component.
3. Register the name in `escape_hatch/__init__.py: CUSTOM_SCENES: dict[str, Callable]`.
4. Invoke from JSON:
   ```json
   { "action": "runCustomScene", "params": { "name": "operation_anaconda", "duration": 8 } }
   ```

Custom scenes bypass the layout system but must still respect the theme palette and timing. Code review required for additions; LLM does not author these.

---

## Schema validation

`schema/validator.py` is called by `pipeline/render_manim.py` before any rendering. It runs four tiers:

1. **Structural** — JSON matches `scene_schema.json` (and coords-banned keys absent anywhere).
2. **Action-level** — each action's `params` matches `action_schemas/<action>.json`. Per-action schemas use `$ref` into `scene_schema.json#/definitions/` for shared enums (timing, effects, anchor pattern, color keys); centralized resolution via `referencing.Registry`.
3. **Semantic** — layout exists for the format (`LAYOUT_FORMATS` map), declared slots match the layout, `at` values within `duration`, no duplicate ids.
4. **Anchors** — every `params.anchor` and `params.target` references an id declared by an event with strictly-earlier sort key (`at`, then phase). Walks events in the same `(at, phase)` order as the scene runner.

Validation errors include the JSON path and a human-readable explanation. The LLM authoring loop reads these to self-correct.

---

## Testing

```
pytest manim_renderer/tests/components/    # render each component at -ql
pytest manim_renderer/tests/golden_frames/ # pixel-diff against references
python manim_renderer/tests/fuzz/run.py    # generates 100 random valid JSONs
```

CI runs all three on every commit. Fuzz failures don't block merge (only crash failures do); they generate a report for review.

---

## Common pitfalls

- **LaTeX missing packages.** `MathTex` failures look like garbled error messages. Confirm `setup_assets.sh` ran successfully.
- **Font fallback.** If Inter or Barlow Condensed aren't installed, Manim silently falls back to defaults. Visual regression. CI test renders a known glyph and checks dimensions.
- **`Text` vs `MarkupText` vs `MathTex`.** `Text` is fastest, supports system fonts. `MarkupText` allows inline styling. `MathTex` for equations only. Don't use `MathTex` for plain labels.
- **Manim coordinate confusion.** Y-axis is up, origin at center. If a component looks shifted, check that you're not treating y like screen coordinates.
- **Animation chaining inside `build()`.** Don't. `build()` constructs static state. Animations happen in `entrance/exit`. Mixing these breaks the layout resolver.
- **Race conditions in CI.** Manim writes to `media/` by default. Set `config.output_file` explicitly per render to avoid cross-test collisions.

---

## Commands

```bash
# render any scene
python pipeline/render.py <scene.json> <clip_name>

# render explicitly via manim engine
python pipeline/render_manim.py <scene.json> <clip_name> --quality preview

# render a single component for development
python -m manim_renderer.tests.components.test_payoff_matrix

# validate JSON without rendering
python -m manim_renderer.schema.validator <scene.json>

# install assets (fonts, LaTeX packages, flag SVGs)
bash manim_renderer/assets/setup_assets.sh
```

---

## When in doubt

- Mimic the existing Mapbox engine's structure. The JSON shape, the action vocabulary, the directory pattern are intentional precedents.
- Read `recap.md` for the design reasoning behind any decision that looks weird.
- Read `plan.md` for what's done, what's in progress, what's out of scope.
- If a rule conflicts with making something work, write a note in the relevant section's "open questions" and proceed cautiously.

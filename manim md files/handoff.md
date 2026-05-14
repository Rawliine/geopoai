# handoff.md — Phase 1 → Phase 2

Read this first if you are picking up work after Phase 1.

---

## TL;DR

Phase 1 (core component library + 8 layouts + 4 mutation actions + 4-tier
schema validation) is **complete**. Both `prisoners_dilemma.json` and
`prisoners_dilemma_vertical.json` render a 60-second narrative end-to-end
using only the JSON DSL.

Phase 2's job is **motion polish + camera + remaining effect vocabulary**.
See "Where to start Phase 2" below.

---

## What was implemented

### Components — 10 total (`COMPONENT_REGISTRY`)

| Action | File | Custom anchors | Bespoke entrances |
|---|---|---|---|
| `showTextCard` | `components/text_card.py` | (standard 9) | (base default) |
| `showStatBlock` | `components/data_viz/stat_block.py` | `value`, `label`, `unit`, `trend`, `sparkline` | `count-up` |
| `showMetricGroup` | `components/data_viz/metric_group.py` | `stat:<i_or_id>` + each child stat id exposed | `staggered` |
| `showCalloutBox` | `components/narrative/callout_box.py` | `head`, `tail` | bubble→leader Succession |
| `showBarChart` | `components/data_viz/bar_chart.py` | `bar:<i_or_label>` | `count-up`, `grow-up` |
| `showLineChart` | `components/data_viz/line_chart.py` | `series:<i_or_label>.start/.end` | `draw-out`, `level-by-level` |
| `showTimeline` | `components/narrative/timeline.py` | `event:<i_or_id>(.label/.date)` + each event id | `level-by-level` |
| `showGameTree` | `components/game_theory/game_tree.py` | `node:<path>` (e.g. `node:root.0.1`) | `level-by-level` |
| `showAllianceWeb` | `components/geopolitical/alliance_web.py` | `node:<id>` + each node id | `level-by-level` |
| `showPayoffMatrix` | `components/game_theory/payoff_matrix.py` | `cell:i,j`, `row:i`, `col:j` | `level-by-level` |

### Mutation actions — 4 total (`ACTION_REGISTRY`)

| Action | File | Targets | Notes |
|---|---|---|---|
| `removeComponent` | `actions/remove_component.py` | any component id | drops from `id_to_mobject` |
| `highlightCell` | `actions/highlight_cell.py` | PayoffMatrix-shaped | overlay, ephemeral (no id) |
| `crossOut` | `actions/cross_out.py` | PayoffMatrix-shaped | strike or dashed style |
| `bestResponseArrow` | `actions/best_response_arrow.py` | PayoffMatrix-shaped | actor-colored arrow |

### Layouts — 8 total (`layouts/{horizontal,vertical}.py`)

`hero`, `split`↔`stacked`, `data-left`↔`data-top`, `trio`↔`trio-stack`,
`title-body`. Format/layout compatibility enforced by
`validator.LAYOUT_FORMATS`.

### Resolvers (`resolvers/`)

- `anchor.py` — 5 tokens (`above`, `below`, `left-of`, `right-of`, `inside`);
  vertical auto-flip; `place_at_anchor` (next_to-based, avoids overlap).
- `size.py` — 5 kinds (`default`, `matrix`, `chart`, `tree`, `web`) × 2
  formats × 3 roles (`small`, `medium`, `large`).

### Effects (`effects/`)

`EffectSpec` dispatch shape — `(name, factory, required, optional)`.

- **Entrances (11):** `fade-in`, `write-in`, `draw-out`, `grow-up`,
  `grow-down`, `slide-left`, `slide-right`, `slide-up`, `slide-down`,
  `level-by-level`, `count-up`.
- **Emphasis (2):** `pulse`, `highlight`.
- **Exits (2):** `fade-out`, `dissolve`.
- `_animations.py:CountUpAnimation` — generic numeric interpolator, drives
  StatBlock and BarChart's per-bar value labels.

### Schema (`schema/`)

- `scene_schema.json` — centralized definitions block (`id_string`,
  `anchor_string`, `timing_name`, `size_role`, `color_role` (=palette key),
  `entrance_effect`, `emphasis_effect`, `exit_effect`, `value_format`,
  `layout_name`). All per-action schemas `$ref` into it.
- 13 per-action schemas, all `additionalProperties: false`.
- `validator.py` — 4 tiers (structural, coords-banned, per-action, semantic
  incl. anchor and duplicate-id with extractors).
- `_ACTION_ID_EXTRACTORS` for `showMetricGroup`, `showTimeline`, `showAllianceWeb`.

### Tests

- `tests/resolvers/` — anchor + size, pure functions.
- `tests/layouts/` — 8 layouts × frame-bounds + slot-non-empty + compat-map.
- `tests/components/` — one file per component, both formats build, anchors work, entrances dispatch.
- `tests/actions/test_mutations.py` — direct unit tests of the three mutations.
- `tests/schema/` — one per-action `_rejection.py` file per registered action.

### Docs

- `manim md files/AGENT.md` — 15 hard rules (rules 9–15 added in Phase 1).
- `manim md files/recap.md` — Phase 1 implementation decisions block (§22a).
- `manim md files/plan.md` — Phase 1 marked complete.
- `scripts/manim/_skill.md` — every action documented with example JSON,
  custom anchors, allowed effects.

---

## What was NOT implemented (deliberately deferred)

These were intentional Phase 1 omissions. Phase 2 picks them up in roughly
this order.

1. **Camera actions** — `cameraZoom`, `cameraPan`, `cameraFocus` (`recap.md`
   §13). `JSONScene` already extends `MovingCameraScene`; the dispatch seam
   in `scene.py:_dispatch_action` is ready. Add three callables to
   `ACTION_REGISTRY` + three schemas + a `resolvers/camera.py` if needed.
2. **Remainder of the 35-effect vocabulary.** Phase 1 ships ~15 (entrances +
   emphasis + exits). Missing: `slam`, `typewriter`, `stagger-in`, `spiral-in`,
   `strike`, `glow`, `shake`, `surround`, `color-shift`, `dim-others`,
   `shrink`, `slide-out-left/right`, `grey-out`, and all 5 transitions
   (`fade`, `wipe-left/right`, `zoom-in/out`). Each is one factory function
   + one `EffectSpec` entry + one schema enum line.
3. **`effects/transitions.py`** — separate module for cross-clip transitions.
   Phase 1 didn't ship it; first transition consumer creates the file.
4. **Asset pipeline** — `manim_renderer/assets/setup_assets.sh` referenced in
   `AGENT.md` line 297 but not yet written. Phase 2 must script installing
   Inter, Barlow Condensed, JetBrains Mono, STIX Two Math, and the LaTeX
   packages (`amsmath`, `amssymb`, `mathtools`). Without this, font fallback
   is silent and breaks visual regression.
5. **CI palette diff** between `manim_renderer/theme/palette.py` and
   `renderer/effects.css` (per `AGENT.md` line 96 + `recap.md` §9 LOCKED).
   Currently asserted in docs but not enforced.
6. **Golden-frame tests** for the top 4 components — `recap.md` §16. Phase 1
   has component build tests but no pixel diff.
7. **LLM-output fuzz harness** — `recap.md` §16. Generates ~100 random valid
   JSONs and renders them at `-ql`. Non-blocking but flags crashes.
8. **`next-to:id` anchor token** — dropped from Phase 1 because it's
   under-specified ("which side?"). Resurrect when content authoring forces
   a clear answer.
9. **Removable mutation overlays.** ✓ **Shipped in Phase 1.5.** Overlays
   are now tracked against host id in `JSONScene._overlays_by_host` and
   auto-clean when host is removed. Optional `params.id` exposes the
   overlay as a top-level id for individual `removeComponent`. AGENT.md
   rule 15 rewritten accordingly.
10. **Force-directed AllianceWeb layout.** Phase 1 ships circular for
    determinism + readability at small node counts. Force-directed
    (Fruchterman-Reingold-lite) is a content-driven upgrade — add it when a
    scene has 10+ nodes and circular looks crowded.
11. **`escape_hatch/` runCustomScene action** — directory referenced in
    `AGENT.md` and `recap.md` §18 but the action isn't registered. Empty
    `__init__.py` exists. Add when a content brief needs it.
12. **Quality-mode wiring through `render_manim.py`.** `_skill.md` documents
    `preview`/`draft`/`full`; `pipeline/render_manim.py` honors these. Verify
    flags map correctly to `-ql`/`-qm`/`-qh` in CI.

---

## Known gaps and follow-ups (surfaced mid-build)

These are concrete TODOs that would have grown Phase 1's scope. They're
testable individually; pick them off in any order.

1. **GameTree path syntax is index-only** — `node:root.0.1` works but
   semantic names (`node:root.left.right`) do not. Add an optional `name`
   field on tree nodes and let `_get_anchor_node` look it up.
2. **GameTree internal schema `$ref`** — `show_game_tree.json` uses
   `#/definitions/tree_node` (recursive local ref). Test
   `test_deeply_nested_children_validate` confirms it works with the
   current `referencing.Registry` config but if you ever hit
   "unresolvable ref" errors when adding a recursive schema, check that
   `Draft7Validator` is constructed with `registry=`.
3. **BarChart can't render negative values.** Bars always grow from `max(0,
   y_min)` upward. A negative-value bar chart needs a baseline-anywhere
   bar component or a sign-aware grow direction. Document is in
   `bar_chart.py:_resolve_color` and the `count-up` factory.
4. **LineChart `value_format` applies only to y-axis.** x_format is a
   separate param. The schema allows both; this matches the convention but
   is undocumented in `_skill.md` (added in PR 1.3).
5. **CountUpAnimation requires `set_value` defined on the class, not the
   instance.** `effects/_animations.py:_class_defines` guards against Manim's
   synthesized setters — if you add a count-up consumer, copy StatBlock's
   `set_value` pattern (re-render text mobject and swap).
6. **Timeline at_label is optional and untyped.** It's the date or `at` string
   the LLM provides ("1939", "Q3 2024", etc.). Schema treats it as opaque.
   If you later need range queries or sorting, parse here.
7. **AllianceWeb edge endpoints sit at node centers, not circle edges.**
   For high-stroke arrows it can look like the line "punches into" the
   circle. Acceptable for Phase 1; fix with a 2D unit-vector trim if the
   visual reads bad.
8. **PayoffMatrix doesn't render the player-strategy axes' titles** beyond
   the player names. If a video needs explicit "Strategy" / "Strategy"
   labels, add an `axis_labels` param.
9. **Mutation overlay z-order.** Tracking is fixed in Phase 1.5 (overlays
   auto-clean with host), but z-order behavior is unchanged — overlays
   are added at default z via `FadeIn`. If multiple overlap, most recent
   wins. If a future mutation needs to go *behind* a host component, use
   `self.scene.add_to_back(overlay)` explicitly.
10. **Schema rejection tests live in `tests/schema/`; component tests in
    `tests/components/`; action tests in `tests/actions/`.** No fixture
    sharing yet. If test counts grow, add `conftest.py` per directory.
11. **`pipeline/render_manim.py` isn't reread in Phase 1.** Verify it passes
    `format` through correctly; the existing tests render via the manim CLI
    not this dispatcher. Smoke-test it before any Phase 2 PR that touches
    rendering options.

---

## Conventions established mid-build (with pointers)

| Convention | Where documented |
|---|---|
| Anchor coords sample at call time, not post-animation | `AGENT.md` rule 9, `recap.md` §22a |
| Two registries: `COMPONENT_REGISTRY` + `ACTION_REGISTRY` | `AGENT.md` rule 10, `registry.py` docstring |
| EffectSpec dispatch (`name, factory, required, optional`) | `AGENT.md` rule 11, `effects/_spec.py` |
| `position_finalized` for absolute-coord geometry | `AGENT.md` rule 12, `components/base.py` |
| `extra_id_registrations` + `_ACTION_ID_EXTRACTORS` sync | `AGENT.md` rule 13, `validator.py` |
| Mutation actions duck-type via `hasattr`, not isinstance | `AGENT.md` rule 14, each `actions/*.py` |
| Mutation overlays are ephemeral (no id) | `AGENT.md` rule 15, mutation file docstrings |
| Sort tiebreak phases: slot=0, overlay=1, timeline=2 | `scene.py` constants, `validator.py` parallel |
| Centralized schema enums via `$ref` to `scene_schema.json#/definitions/` | `validator._make_registry`, every action schema |
| `_slot_bounds` is an internal underscore-key set by scene runner | `scene.py:_dispatch_component`, `_text_fit.py` |
| Chart `_axes_common.py` is private, shared by ≥2 components | `data_viz/_axes_common.py` |

---

## Where to start Phase 2

**First PR (recommended):** complete the effects vocabulary + camera actions.

1. **Add the remaining ~20 effects.** Each is mechanical:
   - Add factory function to `effects/{entrances,emphasis,exits,transitions}.py`
   - Add `EffectSpec(name, factory, required, optional)` to the module's dict
   - Add name to the matching `scene_schema.json#/definitions/<kind>_effect` enum
   - Update `scripts/manim/_skill.md` "Effects vocabulary" section
   - Component schemas that should accept the new effect must update their
     local `effect` enum (or replace with `$ref` if they were already using
     the centralized one)

2. **Add the three camera actions.** Wire them in like the mutation actions:
   - `actions/camera_zoom.py`, `camera_pan.py`, `camera_focus.py`
   - Each takes `ActionContext` and returns an `Animation` that animates
     `ctx.scene.camera.frame`. Manim's `MovingCameraScene` already has the
     plumbing — `ctx.scene.camera.frame.animate.scale(factor)` or
     `.move_to(point)`.
   - Add to `ACTION_REGISTRY`, write per-action schemas, write tests.
   - Camera state interpolates between events with `EASE["emphasis"]` per
     `recap.md` §11.

3. **Drop in `resolvers/camera.py`** if any non-trivial coord math emerges
   (e.g. computing a frame that bounds N targets for `cameraFocus`).

4. **Asset pipeline.** Write `manim_renderer/assets/setup_assets.sh`. The CI
   check that fonts + LaTeX packages are present is gating future visual
   regression work — block all visual PRs until this is in place.

5. **Palette CI diff.** Compare `theme/palette.py` against `renderer/effects.css`.
   `recap.md` §9 says CI enforces equality; make it actually true.

Once camera + remaining effects are in, the next PRs are content-driven —
golden frames, fuzz harness, escape-hatch wiring, removable overlays.
Build only on signal from the orchestrator / content team.

---

## Verification commands

Run these in order. They should all pass before any Phase 2 work begins.

```bash
# 1. Fast suite (schema + resolvers + validator + layouts + components
#    that don't render). Should finish in seconds.
pytest manim_renderer/tests/ -m "not render" -q

# 2. Validate both exit-criteria scenes.
python -m manim_renderer.schema.validator scripts/manim/prisoners_dilemma.json
python -m manim_renderer.schema.validator scripts/manim/prisoners_dilemma_vertical.json

# 3. Render the full PD scenes end-to-end (preview quality).
python pipeline/render.py scripts/manim/prisoners_dilemma.json pd_horizontal
python pipeline/render.py scripts/manim/prisoners_dilemma_vertical.json pd_vertical
# Expect: output/manim/pd_{horizontal,vertical}.mp4 both > 0 bytes; all 8
# components from the scene appear; anchored callouts land on their targets;
# all 3 mutations (highlightCell, crossOut, bestResponseArrow) visibly fire;
# no crashes.

# 4. Regression: the Mapbox engine must still work.
python pipeline/render.py scripts/map/test_scene.json hook_clip

# 5. Phase 0 smoke (hello world).
python pipeline/render.py scripts/manim/hello.json hello

# 6. Layout QA scenes still validate + render.
python -m manim_renderer.schema.validator scripts/manim/qa_layouts_h.json
python -m manim_renderer.schema.validator scripts/manim/qa_layouts_v.json
python -m manim_renderer.schema.validator scripts/manim/qa_stat_features.json
python -m manim_renderer.schema.validator scripts/manim/qa_callout_anchors.json
```

If any of (1) – (5) fails, **do not proceed to Phase 2** — fix or open an
issue first. The handoff is contingent on the green baseline.

---

## Phase 1.5 → Phase 2 / roles+restaging handoff

Phase 1.5 shipped four items (CalloutBox styles, overlay tracking,
validator overflow detection, QA mega scenes) that lay the architectural
seed for the roles+restaging system. The following extension points are
intentionally exposed for that work.

### `BaseComponent.measure(params, format) -> (w, h)` class method
Every component implements it. Pure-math, no Manim mobjects. When the
roles system lands, extend the signature with a `role: str = "primary"`
arg — the solver allocates space by role within the layout. Backward-
compatible because `role` has a default.

**File:** `manim_renderer/components/base.py:46`. Overrides:
`text_card.py`, `data_viz/stat_block.py`, `data_viz/metric_group.py`,
`narrative/callout_box.py`. Other components use the default via
`SIZE_KIND` class attribute.

### `JSONScene._overlays_by_host: dict[str, list[Mobject]]`
Initialized in `scene.py:construct()`. Mutation actions write to it via
`ActionContext.register_overlay`. `removeComponent` reads + clears.

The roles+restaging system's "restage pass" iterates this dict on each
role change: when a host changes role, its overlays travel with it
(parallel Transform). When a host leaves the cast, overlays leave too —
same code path as `removeComponent` today.

**File:** `manim_renderer/scene.py:48`. Writer:
`manim_renderer/actions/_context.py:ActionContext.register_overlay`.

### `manim_renderer/schema/_dry_run.py` walk shape
The walk maintains `live: dict[id, Rect]`, processes events in `(at, phase)`
order, and asks `measure() + place_at_anchor` for each placement. This
is exactly the walk shape the solver's pre-flight needs — when restaging
lands, the walk gains a "current solver" state and the geometry checks
stay identical. Don't duplicate the walk; extend it.

**File:** `manim_renderer/schema/_dry_run.py`. Entry point:
`run_overflow_checks(scene)`.

### `manim_renderer/layouts/base.py:FRAME_BOUNDS`
Per-format frame dims, used by validator AND will be used by the future
solver (when computing "this restage layout fits the frame"). Single
source of truth — don't recompute from Manim config.

**File:** `manim_renderer/layouts/base.py:18`.

### `CalloutStyleSpec` pattern in `_callout_styles.py`
Frozen-dataclass spec with `build_bubble + entrance + exit` factories,
registered in a module-level dict. This is the model for future
visual-variant components: `BadgeSpec` (annotation badges), `ConnectorSpec`
(connection lines between components), `BarStyleSpec` (chart bar fills).
Mirror this shape — additive enum, no `if/elif` chains.

**File:** `manim_renderer/components/narrative/_callout_styles.py`.

### Tolerance constants (tune as needed)
`_dry_run.py:_FRAME_TOL = 0.10` and `_OVERLAP_TOL = 0.05` absorb estimator
error so the validator doesn't flag near-edge cases. If the future solver
produces tighter measurements, these can shrink. If false positives
become a problem, they can grow.

### What roles+restaging should NOT touch
- `BaseComponent` API surface (don't break the contract).
- The schema's `coords-banned` rule — coordinates still never appear in
  JSON. Roles are a higher-level abstraction; solver positions are in
  layout-space coords, hidden from authors.
- `EffectSpec` / `CalloutStyleSpec` shape — both are stable.

### What roles+restaging WILL replace
- `layouts/{horizontal,vertical}.py` static slot dicts — likely become
  solver classes that take a cast and return per-id Rects.
- The static `slot.move_to(rect.center)` placement in `scene.py:_dispatch_component`
  — becomes a solver call.
- Anchors as primary placement mechanism — become hints the solver may
  or may not honor.

When the roles+restaging plan lands, re-read this section first.

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

## Phase 2.0 fixes (PR E, shipped)

Quick wins shipped before the Roles+Restaging architecture lands. None of
these change the architecture; they're patches to the Phase 1.5 surface.

1. **`set_value` uses `Text.become()`** in StatBlock + `_BarValueLabel`.
   Eliminates the `"0.0"` count-up start-frame leak that persisted past
   `removeComponent`. See recap.md §22b update.
2. **Bar chart value-label floor.** Labels for zero/short bars are
   floored at `baseline_y + safe_floor_offset` so they never collide with
   the x-axis tick label band or axis title. See `bar_chart.py` build().
3. **Neon callout style is now three concentric strokes** (outer glow +
   mid glow + border) for a perceptible halo at preview resolution.
   See `_callout_styles.py:_neon_bubble`.
4. **`bracket` callout style dropped.** Schema enum + builder + tests +
   QA scene usages removed. New variants `neon-bold`, `pull-quote`,
   `inline-tag` arrive in PR P with the roles+restaging system.
5. **X-axis title clearance bumped** (`_AXIS_TITLE_BUFF` 0.18 → 0.30) so
   the axis title doesn't crowd into the x-axis tick label band.
6. **`_BarValueLabel.set_value` scene-position fix** (PR E3). The previous
   pattern used a stored build-time LOCAL anchor in the `move_to(...)`
   before `become`, which made labels jump by `-slot.center` on every
   count-up frame — visible as "labels outside the chart" in non-origin
   slots (split-right, stacked-bottom). The fix mirrors `StatBlock.set_value`:
   `new_text.move_to(self._text.get_center())` preserves the current
   SCENE position regardless of parent transforms. Regression test
   `test_count_up_preserves_label_scene_position` asserts this.
7. **Axis title font size reduced** (`caption * 0.95 → caption * 0.75`)
   so `"Payoff"` / `"Outcome"` titles don't dominate small charts.

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

---

# Phase 2 — Roles + Restaging implementation brief (agent-facing)

**You (the implementing agent) are reading this because Phase 2.0 has
shipped and the next big system — Roles + Restaging — is yours.** This
brief is self-contained: you should not need any other document to
execute it. Refer to `AGENT.md` for the hard rules and `recap.md` for
historical context only when something below is ambiguous.

## 1. The architectural change in one paragraph

Today the pipeline is **imperative + static**: each action mutates the
scene (`add X`, `remove Y`), and slot rectangles are fixed in
`layouts/{horizontal,vertical}.py`. When a callout joins a scene, the
host doesn't move; when an element leaves, the hole stays. Roles +
Restaging replaces this with **reactivity**: every component has a
*role* (`hero`/`primary`/`supporting`/`ambient`/`annotation`/`hidden`);
layouts are *solvers* that allocate space proportional to roles for the
current cast; every composition change triggers a FLIP-style restage
pass that Transforms the cast to its new allocation. The author sets the
cast and roles; the engine does the staging.

## 2. Three concepts

**Concept 1 — every component has a role at every instant.** A six-value
enum:

```
hero        — single dominant element; takes most of the frame
primary     — main subject(s); large, full opacity (DEFAULT)
supporting  — present but quieter; dimmed, often shrunk
ambient     — context only; small, very dim (faded sidebar)
annotation  — a callout, badge, label tied to another element
hidden      — present in state but not rendered (kept for fast re-entry)
```

A component declares its role on entry (`params.role`, default
`"primary"`). Any later event can change it via `setRole`. Roles drive
size, opacity, z-order, and position bias inside the layout.

**Concept 2 — layouts are solvers, not fixed rectangles.** Today:
`Layout` is a dataclass with hardcoded `Rect` slots. Tomorrow: each
layout has a `solve(cast, container) -> dict[id, Rect]` method that
allocates space proportional to roles. A generic `flex_solve(cast,
direction, gap, container)` handles 80% of layouts; layouts with special
semantics (e.g., `title-body` pinning the title strip) keep their
custom geometry then delegate to flex for the body cast.

**Concept 3 — the runner restages on every composition change.** Every
event that changes `(id, role)` tuples — show, remove, role change —
fires `_restage()`:

1. **Capture:** for each id in `_id_to_mobject`, record current center +
   scale.
2. **Plan:** call `layout.solve(cast)` for the new cast → target rects.
3. **Animate:** for each id with a non-zero delta, build `Transform(mob,
   target)`. Group via `AnimationGroup` and `self.play()`. New entries
   `FadeIn`; leavers `FadeOut`. Mutations do NOT trigger restage;
   overlays follow their host via a parallel Transform iterated from
   `_overlays_by_host`.

## 3. PR sequence — 14 PRs (F through R)

Each PR ships independently and leaves the tree green.

### PR F — Roles schema plumbing (no behavior change)

**Goal:** add the role vocabulary and `setRole` action stub. Zero
runtime behavior. By landing first, later PRs can rely on the schema.

**Schema:**
- `manim_renderer/schema/scene_schema.json` — add
  `"role_name": { "enum": ["hero","primary","supporting","ambient","annotation","hidden"] }`
- Add optional `"role": { "$ref": "../scene_schema.json#/definitions/role_name" }`
  to all 10 `show_*.json` action schemas.
- Create `manim_renderer/schema/action_schemas/set_role.json` with
  required `target` + `role`, optional `timing`.

**Code:**
- `manim_renderer/actions/set_role.py` — new file. Callable records
  `ctx.scene._roles[target] = role` and returns `None`. Restage hooks
  fire in PR G.
- `manim_renderer/registry.py` — register `"setRole": set_role` in
  `ACTION_REGISTRY`.
- `manim_renderer/scene.py:construct()` — init `self._roles: dict[str, str] = {}`
  next to `_id_to_mobject` and `_overlays_by_host`. On every show
  action, default `_roles[id] = params.get("role", "primary")` (or
  `"annotation"` for `showCalloutBox`).
- `manim_renderer/components/base.py:BaseComponent` — `self.role` attr
  from `params.get("role", "primary")`.

**Tests:**
- `manim_renderer/tests/schema/test_set_role_rejection.py` — accept/reject `set_role` params.
- `manim_renderer/tests/schema/test_role_param_in_show_actions.py` — every component schema accepts `role`.
- `manim_renderer/tests/actions/test_set_role.py` — no-op callable doesn't crash.

### PR G — FLIP restage as no-op pass

**Goal:** implement `JSONScene._restage()` mechanism with no actual
movement. Verify it fires at the right moments without crashing.

**Code:**
- `manim_renderer/scene.py`:
  - Add `_restage_state: dict[str, tuple[np.ndarray, float]]` field.
  - Add `_restage(self, reason: str = "") -> None` method:
    1. Capture: `state = {id: (mob.get_center(), 1.0) for id, mob in self._id_to_mobject.items()}`.
    2. Plan: `targets = self._compute_target_rects()` — for PR G returns identity (same state).
    3. Animate: for each id with non-zero delta, build `mob.animate.move_to(target_center).scale_to(target_w)`. Identity → zero-delta, no-op.
  - Call `self._restage(reason="post-show")` at end of `_dispatch_component`.
  - Call `self._restage(reason="post-remove")` after a successful `removeComponent` dispatch.
  - Call `self._restage(reason="post-set-role")` after `setRole`.

**Tests:**
- `manim_renderer/tests/scene/test_restage_no_op_runs.py` — `_restage("test")` runs cleanly with multiple live components, doesn't change `_id_to_mobject`.
- `manim_renderer/tests/scene/test_restage_fires_after_show.py` — patch `_restage` to count calls; assert one call per `show*` event.

**Overlay parenting under restage — design decision:**
Overlays stay at scene root (Phase 1.5 design). `_restage` iterates
`_overlays_by_host[host_id]` and applies the host's Transform to each
overlay in parallel. This preserves the existing `_overlays_by_host`
contract; do NOT re-parent overlays to host VGroups.

### PR H — `preferred_size(role)` per component

**Goal:** extend `measure()` with a role-aware version the solver consumes.

**Code:**
- `manim_renderer/components/base.py` — add `preferred_size(cls, params, format, role) -> (w, h)` classmethod. Default:
  ```python
  base_w, base_h = cls.measure(params, format)
  scale = ROLE_SCALE[role]
  return (base_w * scale, base_h * scale)
  ```
- `manim_renderer/layouts/base.py` — add `ROLE_SCALE` dict next to `FRAME_BOUNDS`:
  ```python
  ROLE_SCALE = {
      "hero": 1.5, "primary": 1.0, "supporting": 0.7,
      "ambient": 0.4, "annotation": 1.0, "hidden": 0.0,
  }
  ```
- Content-driven components (TextCard, StatBlock, MetricGroup, CalloutBox) override `preferred_size` ONLY if linear scaling doesn't fit their content.

**Tests:**
- `manim_renderer/tests/components/test_preferred_size.py` — for each component, `hero > primary > supporting > ambient`; `hidden` returns `(0, 0)`.

### PR I — Generic flex solver

**Goal:** a reusable pure-math solver function.

**New file:** `manim_renderer/layouts/_flex.py`

```python
def flex_solve(
    cast: list[tuple[str, str, tuple[float, float]]],  # (id, role, preferred_size)
    *,
    container: Rect,
    direction: Literal["horizontal", "vertical"],
    gap: float = 0.5,
    align: Literal["center", "start", "end"] = "center",
) -> dict[str, Rect]:
    """Allocate `cast` along `direction` inside `container`. If preferred
    sizes overflow, proportionally shrink. Center on cross-axis."""
```

**Algorithm:**
1. Sum preferred sizes along axis + (n-1) gaps. If overflow:
   `scale = (container_axis - (n-1)*gap) / sum_preferred`; apply to every entry.
2. Position sequentially with running offset; apply `align`.
3. Center on cross-axis.

**Tests:**
- `manim_renderer/tests/layouts/test_flex_solve.py`:
  - One primary fills container
  - Two primaries split 50/50
  - Primary + annotation → 60/40 (annotation gets lower allocation)
  - Oversized cast shrinks proportionally
  - Respects gap
  - Empty cast returns `{}`

### PR J — Convert `split` layout to solver (proof point)

**Goal:** prove the solver pattern on the simplest two-element layout.

**Code:**
- `manim_renderer/layouts/base.py` — `Layout` gets `solve(cast, container) -> dict[id, Rect]`. Default implementation returns hardcoded slot rects (backward compat).
- `manim_renderer/layouts/horizontal.py` — `split` Layout's `solve` method delegates to `flex_solve` with `direction="horizontal"`.
- `manim_renderer/layouts/vertical.py` — `stacked` Layout same with `direction="vertical"`.
- `manim_renderer/scene.py:_compute_target_rects` — call `self._layout.solve(self._cast())` where `_cast()` returns `[(id, role, preferred_size) for id in _id_to_mobject]`.

**Backward compat:** when cast has exactly one component per slot AND no annotations, `solve` returns the same hardcoded slot rects. Existing PD scenes render identically.

**New behavior:** when cast has multiple components OR has annotations, `solve` re-allocates via `flex_solve`. This is when the host *moves* to make room.

**Tests:**
- `manim_renderer/tests/layouts/test_split_solver.py`:
  - One component per slot matches static behavior
  - Two primaries in same slot → side-by-side allocation
  - Primary + annotation → 60/40 redistribution
- Integration: re-render `prisoners_dilemma.json` with no visual regression.

### PR K — Convert remaining layouts to solvers

Each layout implements `solve(cast, container)`:
- `hero` — single-slot, full `flex_solve` over the cast
- `data-left`/`data-top` — narrow data + wider body; `flex_solve` per slot
- `trio`/`trio-stack` — three-column / three-row `flex_solve`
- `title-body` — title slot pinned (no solver); body slot `flex_solve` over body cast

**Files:** `manim_renderer/layouts/horizontal.py`, `vertical.py`.

**Tests:** per-layout solver tests in `manim_renderer/tests/layouts/`.

### PR L — Subject-based callout placement

**Goal:** replace `anchor` with `subject` for annotations. Solver picks the side.

**Schema:**
- `manim_renderer/schema/action_schemas/show_callout_box.json` — `anchor` becomes optional; add optional `subject`. Schema enforces "at least one of `anchor` or `subject`" via `oneOf`.
- `manim_renderer/schema/scene_schema.json` — define `subject_string` allowing both bare id (`"pd"`) and refined (`"pd:cell:1,0"`).

**Code:**
- `manim_renderer/components/narrative/callout_box.py` — accept `subject`; when set, store for the runner; defer side selection to solver.
- `manim_renderer/scene.py:_dispatch_component` — when callout has `subject` (no `anchor`), don't call `place_at_anchor`; let `_restage` solve placement.
- New helper `manim_renderer/resolvers/subject_placement.py` — given a subject mobject + available frame space + layout direction, returns the preferred anchor token + buff. Prefer `right-of` in horizontal, `below` in vertical.

**AGENT.md addendum to rule 9:** "Anchor coords still sample at call time, BUT subject-based callouts re-sample after each restage Transform completes. Use `position_finalized` (called once at instantiation) for static anchor work; use a new `reposition(host_bbox)` hook (added in PR G if not earlier) for restage-aware leader lines."

**Tests:**
- `manim_renderer/tests/resolvers/test_subject_placement.py`:
  - Picks `right-of` in horizontal when space available
  - Picks `below` in vertical
  - Falls back to alternate side when preferred is blocked
- Integration: rewrite one callout in `qa_mega_h.json` to use `subject`, confirm visual quality.

### PR M — Color inheritance from subject

**Goal:** a callout about cell `[1, 0]` (which is `actor_a`-colored) automatically uses `actor_a` as its accent.

**Code:**
- `manim_renderer/components/narrative/callout_box.py:_resolve_accent_hex` — when `subject` is set AND no explicit `color`, walk the subject lookup:
  - Subject = `"pd:cell:i,j"` → look up PayoffMatrix's actor color for that cell's dominant payoff (row → actor_a, col → actor_b).
  - Subject = top-level id with known palette color (StatBlock with `color: "actor_a"`) → inherit.
  - Fallback: `highlight`.
- New helper `manim_renderer/resolvers/subject_color.py` — encapsulates the inheritance rules.
- Explicit `color` param always wins.

**Tests:**
- `manim_renderer/tests/resolvers/test_subject_color.py`:
  - `pd:cell:1,0` inherits `actor_a`
  - StatBlock `actor_a` subject inherits `actor_a`
  - Falls back to `highlight` when subject has no color
  - Explicit `color` param overrides inheritance

### PR N — Validator solver-aware composition tier

**Goal:** validation that says "this scene asks for 5 primaries in `split` — split can fit 2".

**Code:**
- `manim_renderer/schema/_dry_run.py` — replace `check_slot_fits`/`check_anchor_overflows`/`check_collisions` with a single solver-based walker:
  1. Walk events in `(at, phase)` order maintaining the cast `(id, role)`.
  2. At each event, call `layout.solve(cast)` to get planned rects.
  3. Assert each rect fits within the frame.
  4. Assert no pairwise overlap among planned rects.
- Keep the old function names as wrappers for backward compat with existing tests.
- New error class: `[composition-fit] event#N: <action> with 5 primaries in 'split' overflows; layout can fit 2. Suggest 'trio' or sequence.`

**Tests:**
- Update `manim_renderer/tests/schema/test_overflow_detection.py` for new error format.
- Add `test_composition_too_many_primaries.py`.
- Add `test_composition_callout_makes_host_shrink.py` — primary + annotation both fit; assert solver re-allocates.

### PR O — `showCalloutSequence` action

**Goal:** explicit sequencing — one callout at a time, never two simultaneous.

**JSON shape:**

```json
{
  "at": 20.0,
  "action": "showCalloutSequence",
  "params": {
    "id": "seq-1",
    "callouts": [
      { "subject": "pd:cell:1,0", "text": "Defection beats cooperation here." },
      { "subject": "pd:cell:0,1", "text": "Symmetric for the other player." },
      { "subject": "pd:cell:1,1", "text": "Both defect — Nash equilibrium." }
    ],
    "hold_each": "slow",
    "transition": "fast",
    "style": "neon"
  }
}
```

Each callout enters, holds, fades out, next enters. Validator counts the sequence as one annotation at any moment. The sequence's `id` can be `removeComponent`'d to cancel mid-stream.

**Code:**
- `manim_renderer/actions/show_callout_sequence.py` — new action. Hybrid: instantiates one CalloutBox at a time, chains entrance/exit animations via `Succession`. Lives in `ACTION_REGISTRY` because it doesn't register a single top-level id; inner callouts are ephemeral.
- `manim_renderer/registry.py` — register `showCalloutSequence`.
- `manim_renderer/schema/action_schemas/show_callout_sequence.json` — schema with required `callouts` (array of callout params), optional `hold_each`/`transition`/`style`.

**Tests:**
- `manim_renderer/tests/actions/test_show_callout_sequence.py`:
  - Sequence renders callouts in order
  - Only one callout live at a time
  - Each inner callout's params validate
  - `removeComponent(target=seq-1)` cancels remaining callouts

### PR P — Three new callout styles

**Goal:** replace the dropped `bracket` with three thoughtfully-designed variants.

**New styles:**

1. **`pull-quote`** — large stylized accent. No bubble, no leader. Big accent quote marks (`"` and `"`) bracket the text in `display` font (Barlow Condensed), 1.5× size. Fades in word-by-word (typewriter-lite). For thematic emphasis.

2. **`inline-tag`** — small chip overlay or beside-subject. No leader. Accent-colored fill with `pick_text_color(accent)` text. For short labels ("Equilibrium", "Cooperate", actor names). 1-line max.

3. **`neon-bold`** — same neon visual language but cranked up. 5 layers instead of 4 (extra outer-outer glow). Optional pulsing animation post-entrance. For headline moments.

**Files:**
- `manim_renderer/components/narrative/_callout_styles.py` — add 3 specs to `CALLOUT_STYLES`.
- `manim_renderer/schema/scene_schema.json` — extend `callout_style` enum to `["neon", "card", "glass", "pull-quote", "inline-tag", "neon-bold"]`.
- `manim_renderer/components/narrative/callout_box.py` — `inline-tag` may need leader suppression (skip `position_finalized` leader work when style is `inline-tag`).
- Tests per style + schema rejection updates.

**Style choice guide** (document in `_skill.md`):
- `neon` — default. Punchy accent border with halo. Best general-purpose.
- `neon-bold` — when you want it to dominate visually.
- `card` — neutral annotation, doesn't compete for attention.
- `glass` — translucent emphasis over busy backgrounds.
- `pull-quote` — thematic emphasis, single-sentence summary of a beat.
- `inline-tag` — labels/badges on subjects. No leader.

### PR Q — Re-author PD + new QA scenes

**Goal:** prove the system on real content.

**Re-author existing scenes:**
- `scripts/manim/prisoners_dilemma.json` + `prisoners_dilemma_vertical.json`:
  - Add `role` to each component (matrix → primary, KPIs → supporting before fade).
  - Replace static `anchor` callouts with `subject` callouts where natural.
  - Use `showCalloutSequence` for the IESDS callouts about each cell.

**New QA scenes:**
- `scripts/manim/qa_roles.json` (horizontal) + `qa_roles_v.json` (vertical) — exercise role transitions:
  1. One primary fills the frame (hero role).
  2. Second primary enters → restage to side-by-side.
  3. One demotes to supporting → other expands.
  4. Annotation arrives → both primaries shrink slightly.
  5. Annotation leaves → primaries restore.
  6. Focus pull via `setRole(target: X, role: hero)` → others go ambient.
- `scripts/manim/qa_sequence.json` — exercise `showCalloutSequence` with 3-4 callouts on a single matrix.

**Tests:**
- `manim_renderer/tests/schema/test_qa_roles_scenes_validate.py` — schema OK.
- Visual regression: `prisoners_dilemma.json` renders without obvious regression vs. Phase 2.0 baseline.

### PR R — Documentation sweep

**Update every md file:**

- `manim md files/AGENT.md`:
  - **New rule 17:** "Components have a role at every instant. Roles drive size/opacity/z-order via the layout solver. Default role is `primary`. Set via `params.role` or `setRole` action."
  - **New rule 18:** "Restage fires after every composition change (show, remove, setRole). Mutations don't trigger restage; overlays follow the host via the parallel-Transform walker in `_overlays_by_host`."
  - **Rule 9 addendum:** "Subject-based callouts re-sample anchor after each restage Transform via `reposition(host_bbox)` hook."
  - "How to add a new component" step 5: "Override `preferred_size(params, format, role)` only if linear scaling by role doesn't fit your component."

- `manim md files/plan.md`:
  - Mark **Phase 2** DONE with the shipped list.
  - Drop the original Phase 2 "Effects, motion, camera" entry — that scope moves to **Phase 3**.

- `manim md files/recap.md`:
  - New **§22c — Phase 2 implementation decisions**, ~6 entries:
    1. Role enum: why these 6 and not more
    2. Restage timing: after every composition change, not on mutations
    3. FLIP technique: why over direct positioning
    4. Solver-per-layout vs single generic: trade-off and resolution
    5. Subject-based vs anchor-based placement: when to use which
    6. Color inheritance: opt-in via subject, explicit always wins
  - Add ~6 rows to **§22 Decision log**.

- `manim md files/handoff.md`:
  - Strike this Phase 2 brief (it's done).
  - Add a new **Phase 2 → Phase 3** section covering camera (cameraZoom/Pan/Focus), remaining ~20 effects, content-driven component expansion.

- `scripts/manim/_skill.md`:
  - Add **Roles** section with the 6-value vocabulary + when to use each.
  - Add **`setRole`** action documentation.
  - Add **`subject`** param to `showCalloutBox` section + when to use vs `anchor`.
  - Add **`showCalloutSequence`** action documentation.
  - Update **callout styles** list — add `neon-bold`, `pull-quote`, `inline-tag`.
  - Add **style choice guide**.

- `README.md`:
  - Phase line: `Phases 0–2 live: dispatcher, 10 components, 8 layout solvers, 4 mutations with auto-cleanup overlays, 6 callout styles (neon default), validator overflow detection, role-based composition + restaging.`

## 4. Architectural seams Phase 2 reuses (don't re-implement)

| Seam | Location | What Phase 2 does with it |
|---|---|---|
| `BaseComponent.measure(params, format)` | `manim_renderer/components/base.py:46` | Extended to `preferred_size(params, format, role)` in PR H. |
| `JSONScene._overlays_by_host` | `manim_renderer/scene.py:48` | `_restage` iterates this when a host moves. |
| `manim_renderer/schema/_dry_run.py` | full file | The walk shape becomes solver-aware in PR N. |
| `manim_renderer/layouts/base.py:FRAME_BOUNDS` | top of file | Consumed by `flex_solve` container clamping. |
| `CalloutStyleSpec` pattern | `manim_renderer/components/narrative/_callout_styles.py` | Model for `pull-quote` / `inline-tag` / `neon-bold` in PR P. |
| `ActionContext.register_overlay` | `manim_renderer/actions/_context.py` | Unchanged; restage iterates the same registry. |
| `EffectSpec` dispatch | `manim_renderer/effects/_spec.py` | Unchanged; effects compose with restage's Transform. |

## 5. Implications + blind spots (10 risks)

1. **Manim Transform on disparate mobject types may fail.** Restage's Transform walk has to handle: `BaseComponent` subclasses (VGroup), CalloutBox (custom build), mutation overlays (Rectangle/Line/Arrow). Use `mob.animate.move_to(...).scale(...)` rather than raw `Transform(old, new)` — it's more permissive. Test Transform on each component type in PR G.

2. **Existing tests may break under restage.** Component tests construct mobjects and check anchors at known positions. PR G's no-op restage doesn't move anything; PR J onward may shift positions. Update affected tests in the PR that breaks them. DO NOT silence tests; if a test fails because restage moved an element, the new position is the truth.

3. **`position_finalized` semantics under restage.** Currently fires once at instantiation. Add a new `reposition(host_bbox)` hook in PR G/L that fires after each restage Transform completes — CalloutBox is the only current consumer; future components may need it.

4. **z-order under restage with overlays.** Overlays sit at scene root. When restage Transforms a host, overlays Transform in parallel — z-order is preserved by add-order. If a host scales smaller, overlays stick out from the host's bbox; visually fine. If a future mutation needs to go behind a host, use `self.scene.add_to_back(overlay)` explicitly.

5. **Validator dry-run cost grows.** Today's dry-run is sub-millisecond. PR N calls `layout.solve(cast)` at each event — still pure math but with more allocations. Estimate ~50ms for a 100-event scene. Acceptable. Cache solver results per cast hash if it becomes a bottleneck.

6. **Subject-based callouts depend on the subject existing at restage time.** If the subject is removed before the callout, the callout has no anchor. Validator catches at compose-time. Runtime: gracefully fall back to center-screen + log warning. Test for this in PR L.

7. **`hidden` role semantics.** A hidden component is still in the cast (occupies state) but not rendered. The solver allocates zero space. When un-hidden (role → primary), the solver re-allocates and the component fades in. Test the cycle in PR H.

8. **Camera (deferred to Phase 3).** Doesn't conflict with restage. Document this in the Phase 3 handoff (PR R).

9. **Manim's `Text.become()` for count-up.** Already wired in Phase 2.0 (PR E1). If you touch the count-up code, preserve the `become()` pattern — `remove()/add()` leaks the start frame.

10. **Existing PD scenes are the regression test.** Every PR from F onward must keep `prisoners_dilemma.json` validating and rendering without visual regression. PR Q re-authors them to use the new model; until then they exercise the backward-compat path.

## 6. Verification (full run after PR R)

```bash
# Every test
pytest manim_renderer/tests/ -q

# Validate every scene
for s in scripts/manim/*.json; do
  echo -n "$s: "
  python -m manim_renderer.schema.validator "$s" 2>&1 | head -1
done

# Render the new role-aware scenes
python pipeline/render.py scripts/manim/qa_roles.json qa_roles
python pipeline/render.py scripts/manim/qa_roles_v.json qa_roles_v
python pipeline/render.py scripts/manim/qa_sequence.json qa_sequence

# Render the re-authored PD scenes
python pipeline/render.py scripts/manim/prisoners_dilemma.json pd_h
python pipeline/render.py scripts/manim/prisoners_dilemma_vertical.json pd_v

# Mapbox regression
python pipeline/render.py scripts/map/test_scene.json hook_clip
```

**Visual checks after PR R:**
- Restage visible: in `qa_roles.json`, when a 2nd primary enters split-left, the existing primary visibly shrinks and slides to make room — single fluid motion, no pop-in.
- Subject + color inheritance: in re-authored PD, the callout about row-0 has `actor_a` border color, points to that row.
- Sequence flow: in `qa_sequence.json`, 3 callouts play one after another, never overlapping spatially or temporally.
- PD scenes look BETTER than the Phase 2.0 baseline, not regressed.

## 7. Suggested ordering

Mergeable independently in this order:

PR F → PR G → PR H → PR I → PR J → PR K → PR L → PR M → PR N → PR O → PR P → PR Q → PR R

Each shipping point leaves the tree green. If you find a PR is bigger than expected, split rather than skip — the order matters because later PRs depend on earlier ones.

**Start with PR F.** It's the smallest, lowest-risk change and unblocks every PR after it.

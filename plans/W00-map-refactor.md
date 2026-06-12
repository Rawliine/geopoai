# W00 — Map layer refactor into `map_renderer/` package

Branch: `agents/w00-map-refactor` · **Solo lane: nothing else runs until merged.**

## Goal
Restructure the scattered map engine (pipeline/render_scene.py + renderer/ +
config/ + root docs) into a self-contained `map_renderer/` package mirroring
`manim_renderer/` and `broll/`, and split the monolithic effects.js/effects.css
into per-family modules with a self-registration pattern — so later lanes
(W11/W12/W13/W22) can work in parallel without sharing files.

**Move + split only. Zero behavior change. No new features.**

## Read first
CLAUDE.md · pipeline/render_scene.py · renderer/map.html · renderer/effects.js
(note `executeTimelineAction` switch at ~line 719) · config/prepare_maps.py

## Checklist

### T1 — Golden frames (before touching anything)
Render deterministic golden frames for regression:
```bash
python pipeline/render_scene.py scripts/map/test_scene.json w00_golden_a
python pipeline/render_scene.py scripts/map/MA_AG.json w00_golden_b
```
Extract 8 evenly spaced PNG frames from each MP4 with ffmpeg into
`tests/golden/w00/`. Commit them (they are deleted in T7).

### T2 — Package skeleton + Python moves
```
map_renderer/
  __init__.py
  runner.py            ← logic from pipeline/render_scene.py
  resolver.py          ← country/version resolution split out of runner
  data_prep/
    __init__.py
    prepare_maps.py    ← from config/prepare_maps.py
    map_versions.json  ← from config/
    map_aliases.json   ← from config/
  web/                 (T3)
  schema/scene.schema.json   ← stub: {"$schema":..., "title":"map scene","type":"object"} only
  docs/SKILL.md        ← moved map_animation_skill.md (verbatim; W01 rewrites)
  tests/               ← move tests/test-*.html here; keep tests/test_data_pipeline.py
                         at top level but update its imports
```
Keep `pipeline/render_scene.py` and `config/prepare_maps.py` as thin shims
(import + delegate, with a deprecation comment). Keep `data/maps/` and
`data/.cache/` paths unchanged so existing downloads stay valid.
`pipeline/render.py` dispatcher must keep working unmodified or with an
import-path fix only.

### T3 — Web assets move + JS/CSS split
```
map_renderer/web/
  map.html             ← from renderer/
  vendor/turf.min.js   ← vendor @turf/turf (pinned version, committed)
  vendor/flubber.min.js← vendor flubber (pinned, committed)
  css/base.css         ← layout, layers, label base styles, GPU hints, :root vars
  css/fills.css        ← fill-* rules        ┐
  css/borders.css      ← border-* rules      │ split of renderer/effects.css,
  css/arrows.css       ← arrow-* rules       │ rules verbatim
  css/labels.css       ← label-* rules       ┘
  css/atmosphere.css   ← empty stub with header comment
  js/core/registry.js  ← NEW (below)
  js/core/runtime.js   ← runTimeline, createDeterministicRuntime, executeTimelineAction
  js/core/reproject.js ← reproject, bindReproject, toPixel
  js/core/utils.js     ← restartAnimation, curvedPath, polylinePath, straightPath,
                         animateTravelDot, typewriterReveal, animateCounter, _elasticOut
  js/effects/fills.js  ← applyFill, _createFillSVG, _applyWipeProgress, pulseRing
  js/effects/borders.js← applyBorder, removeBorder, _geojsonToBorderLines
  js/effects/arrows.js ← drawArrow, removeArrow, _triggerArrowExit
  js/effects/labels.js ← showLabel, removeLabel, clearOverlay
  js/effects/camera.js ← flyTo + cameraShake handling extracted from the switch
  js/effects/atmosphere.js ← stub (registers nothing yet)
  js/effects/models3d.js   ← stub (registers nothing yet)
```
`registry.js`: `MapEffects.registerAction(name, fn)` + `MapEffects.getAction(name)`.
Convert the `executeTimelineAction` switch into registry lookups; each effects
module self-registers its action names (`applyFill`, `removeLayer`,
`applyBorder`, `removeBorder`, `drawArrow`, `removeArrow`, `pulseRing`,
`showLabel`, `removeLabel`, `clearOverlay`, `flyTo`, `cameraShake`).
`map.html` gets script tags for vendor + core + ALL effects modules (including
stubs) in that order — later lanes must never edit map.html to add a file.
Update `runner.py` to load `map_renderer/web/map.html`.

### T4 — Root legacy to archive
`git mv Generation_map.py archive/`. Move tracked legacy data refs
(`data/ne_10m_admin_0_countries.zip`, `.featurecollection.geojson`,
`data/ne_10m_admin_0_countries_extracted/`, `data/countries/` — whichever are
git-tracked) to `archive/` or remove from tracking if duplicated by the
versioned scheme. Note each decision in the report.

### T5 — Fix references
Grep repo-wide for `renderer/`, `render_scene`, `prepare_maps`,
`map_animation_skill` and fix paths in: pipeline/render.py, tests, README,
scripts. (CLAUDE.md content is W01's job — only fix paths that would break
commands.)

### T6 — Regression check
Re-render T1's two scenes, extract the same 8 frames, compare against golden
(`ffmpeg`/PIL diff; mean abs pixel diff < 2/255 per frame). Run
`pytest tests/ -x` and open each `map_renderer/tests/test-*.html` check they
still load their JS (update their script paths).

### T7 — Cleanup
Delete `tests/golden/w00/`, delete now-empty `renderer/`. Final full-tree
`ls` in the report.

## Out of scope
New effects, tokens, schema content, docs rewrites, vertical format.

## Acceptance (lane-level)
`python pipeline/render.py scripts/map/test_scene.json w00_final` and
`python pipeline/render.py scripts/manim/hello.json w00_manim_check` both
succeed; pixel regression in T6 passed; no file named effects.js remains.

## Report
Per item: what moved where, every reference fixed, regression numbers.

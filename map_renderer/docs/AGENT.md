# AGENT.md — map renderer working rules

Read this before editing anything under `map_renderer/`. Companion docs:
`SKILL.md` (how to author scene JSON) and `recap.md` (why the layer is shaped
this way).

## What this layer is

The map renderer turns a map scene JSON into an MP4 by driving a headless
Mapbox GL JS page (`web/map.html`) with Playwright and encoding the result with
ffmpeg. It renders country fills, animated borders, arrows, labels, pulse rings,
and camera moves over a Mapbox base map.

## Layout

```
map_renderer/
  runner.py            # Playwright driver + ffmpeg encode (entry: render_scene)
  resolver.py          # country name + map-version → GeoJSON resolution
  data_prep/
    prepare_maps.py    # downloads/processes Natural Earth → versioned GeoJSON
    map_versions.json  # dataset manifest (tracked)
    map_aliases.json   # short alias → canonical version (tracked)
  schema/scene.schema.json
  web/
    map.html           # Mapbox page; exposes playScene / loadScene / stepTo
    vendor/            # pinned turf.min.js, flubber.min.js (committed)
    css/{base,fills,borders,arrows,labels,atmosphere}.css
    js/core/{registry,runtime,reproject,utils}.js
    js/effects/{fills,borders,arrows,labels,camera,atmosphere,models3d}.js
  docs/                # this trio + SKILL.md
  tests/               # browser test-*.html harnesses
```

Entry points: the unified dispatcher `pipeline/render.py` routes `"renderer":
"mapbox"` scenes to `pipeline/render_scene.py` (a thin shim) →
`map_renderer.runner.render_scene`. `config/prepare_maps.py` is a shim onto
`map_renderer.data_prep.prepare_maps`.

## The effect-registration contract (do not break)

`web/js/core/registry.js` exposes `MapEffects.registerAction(name, fn)` and
`MapEffects.getAction(name)`. Each effects module **self-registers** its action
names at load; `runtime.js` dispatches timeline actions via registry lookup.

- `map.html` already has `<script>` tags for vendor + all core + **all** effects
  modules (including the `atmosphere`/`models3d` stubs). **Never edit `map.html`
  to add a module** — add your action registrations inside the existing module
  file for your family. This is what lets W11–W22 work in parallel without
  touching shared files.
- Add a new effect by registering it in the right family module and adding its
  CSS class to the matching `web/css/<family>.css`. Keep deterministic
  (`stepTo`) behavior working, not just realtime.

## Rules

- **No hardcoded visual constants.** Colors, fonts, glow, timing, and safe areas
  come from `config/design_tokens.json` (via `web/css/tokens.css`, established in
  W02). Don't inline hex or font names in CSS or JS.
- **Frozen contracts.** `schema/scene.schema.json` and `config/design_tokens.json`
  change only via the lead — never inside a lane.
- **New user-facing surface** (actions, effects, params) gets documented in
  `map_renderer/docs/fragments/<lane>.md`; the lead merges fragments into
  `SKILL.md` at integration. Never edit `SKILL.md` directly in a feature lane.
- **Keep the shims working.** `pipeline/render_scene.py` and
  `config/prepare_maps.py` must keep delegating; don't move logic back into them.
- **Two render modes must both work.** Realtime (WebM capture) and deterministic
  (`_deterministic: true`, one `stepTo(t)` screenshot per frame).

## Country / map-version data

Per scene action, version resolves `params.version` → scene `_map_version` →
`"latest"`, then through `map_aliases.json`. If the dataset isn't present,
`resolver.py` auto-provisions it via the manifest. Generated geometry lives in
`data/maps/<version>/` (gitignored); only `data_prep/*.json` manifests are
tracked. See `recap.md` for the rationale (incl. the Morocco / Western Sahara
merged-vs-split decision).

## Testing

```bash
python pipeline/render.py scripts/map/MA_AG.json smoke      # full render smoke
pytest tests/test_data_pipeline.py -v                       # data prep
pytest tests/test_w00_map_frame_regression.py -v            # deterministic pixel regression
```

The `tests/test-*.html` harnesses under `map_renderer/tests/` load the JS
modules directly in a browser for effect debugging.

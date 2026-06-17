# recap.md — map renderer decisions, reasoning, open questions

Companion to `SKILL.md` (how to author scenes) and `AGENT.md` (working rules).
This file is the *why*. Status tags: `[LOCKED]` settled, `[FLUID]` may change.

---

## 1. Why a `map_renderer/` package (the W00 restructure)

Before W00 the map engine was scattered: `pipeline/render_scene.py` held the
driver, `renderer/` held a monolithic `map.html` + `effects.js` + `effects.css`,
and map config sat in `config/`. That layout made parallel work impossible —
every feature lane would have edited the same two giant files.

W00 restructured it into a self-contained package mirroring `manim_renderer/`
and `broll/`: Python (`runner.py`, `resolver.py`, `data_prep/`), web assets
(`web/`), schema, docs, and tests all under `map_renderer/`. The hard constraint
was **move + split only, zero behavior change** — a deterministic pixel
regression (`tests/test_w00_map_frame_regression.py`, mean abs diff < 2/255)
guards that nothing rendered differently after the move.

`[LOCKED]` — the package boundary. Layout details `[FLUID]`.

---

## 2. Per-family JS/CSS split + self-registration

The monolithic `effects.js` (a big `executeTimelineAction` switch) and
`effects.css` were split into per-family modules: `fills`, `borders`, `arrows`,
`labels`, `camera`, plus `atmosphere` and `models3d` stubs. The switch became a
registry: `registry.js` exposes `registerAction`/`getAction`, and each module
self-registers its actions at load.

Why: later lanes (W11 territory = fills/borders, W12 flow-text = arrows/labels,
W13 camera/atmosphere, W22 = models3d) each own disjoint files and can run in
parallel without merge conflicts. `map.html` is pre-wired with `<script>` tags
for **every** module including the empty stubs, so no lane ever has to edit the
shared HTML to add a file.

`[LOCKED]` — registry pattern + pre-wired map.html. Stub modules are
deliberately empty until their lanes fill them.

---

## 3. Back-compat shims

`pipeline/render_scene.py` and `config/prepare_maps.py` were kept as thin shims
that import and delegate into `map_renderer`. Existing scripts, docs, and muscle
memory keep working; the canonical implementations moved without a flag day. The
unified dispatcher `pipeline/render.py` routes by the scene's `"renderer"` field.

`[FLUID]` — shims can be removed once nothing references the old paths.

---

## 4. Country-data versioning — manifest in git, data out of git

The **manifest** (`data_prep/map_versions.json`) and **aliases**
(`data_prep/map_aliases.json`) are committed: they describe every downloadable
dataset and its source. The **generated geometry** (`data/maps/<version>/`) and
the download cache (`data/.cache/`) are gitignored — they are large, derived,
and reproducible from the manifest.

This gives lockfile-style reproducibility (the manifest pins what to fetch)
without bloating the repo with hundreds of MB of GeoJSON. A fresh clone
self-provisions on first render.

`[LOCKED]` — manifest-tracked, data-gitignored.

---

## 5. Resolution order and the auto-provision path

Per timeline action (only `applyFill` / `applyBorder` carry country refs),
version resolves: `params.version` → scene `_map_version` → `"latest"`, then
through the alias table. If the resolved dataset file is missing, `resolver.py`
shells out to `prepare_maps.py --from-manifest` to download it, then falls back
to `"latest"` if the requested version still can't be loaded.

Lookups prefer a **fast path** — pre-extracted `data/maps/<version>/countries/*.geojson`
files indexed by several name keys (ADMIN, NAME, SOVEREIGNT, ISO codes, …) — and
fall back to parsing the full `countries.featurecollection.geojson`. When a name
matches multiple features, the largest-area feature wins, so "Morocco" resolves
to the mainland polygon, not a sliver.

`[FLUID]` — name-key list and ranking heuristics can grow as datasets vary.

---

## 6. Morocco / Western Sahara — why multiple versions exist

The disputed status of Western Sahara is the reason the map layer is
version-aware rather than shipping one canonical world map:

- `latest` (NE 10m countries) merges Morocco + Western Sahara into one polygon.
- `1991_ceasefire` / `ceasefire` (NE 10m map units) keeps them as **separate**
  polygons — the dataset to use for ceasefire / disputed-territory scenes.
- `ne_10m_sovereignty` distinguishes sovereign states from dependent territories.
- `ne_50m_countries` / `fast` and `ne_110m_countries` / `global` trade detail for
  render speed (wide-angle and planetary shots).

Choosing the dataset is an **editorial** decision the scene author makes per
clip, not a hardcoded default. That is the whole point of the versioning system.

`[LOCKED]` — version-per-clip editorial control. Specific dataset list `[FLUID]`.

---

## 7. Island handling

Country features are often MultiPolygons that include distant islands. By default
the resolver keeps only the largest polygon (`_include_islands: false`) so a
country fill doesn't paint specks across the ocean. Authors opt into full
geometry with `_include_islands: true` (scene) or `include_islands` (per action).

`[FLUID]` — a future per-region allowlist could be smarter than largest-polygon.

---

## 8. Deterministic vs realtime rendering

Two modes share one effects codebase. **Realtime** records the page as WebM
(fast, slight frame variation). **Deterministic** (`_deterministic: true`) calls
`stepTo(t)` once per frame and screenshots — repeatable motion with `_seed`,
used for final delivery. Every effect must implement both: CSS-driven animation
for realtime and a `stepTo`-driven equivalent for deterministic. Infinite CSS
effects (glow, marching ants, breathe) run correctly in both.

`[LOCKED]` — both modes are first-class; new effects must support both.

---

## 9. Open questions (fluid)

- **Tokens migration.** W02 introduces `config/design_tokens.json` →
  `web/css/tokens.css`; existing literal colors in the split CSS need to migrate
  to vars without changing rendered output.
- **Schema depth.** `schema/scene.schema.json` is currently a stub; how strict
  per-action validation should become (vs. the Manim validator's three tiers) is
  open.
- **3D and atmosphere.** `models3d.js` / `atmosphere.js` are stubs awaiting
  W13/W22; their interaction with the deterministic `stepTo` loop needs care.
- **Resolver ambiguity.** Largest-area name matching is a heuristic; rare
  collisions (same name across datasets) may need explicit disambiguation.

---

## 10. Decision log

| Decision | Section | Status |
|---|---|---|
| `map_renderer/` package boundary | §1 | LOCKED |
| Per-family modules + registry self-registration | §2 | LOCKED |
| Pre-wired map.html (no per-lane edits) | §2 | LOCKED |
| Back-compat shims for render_scene / prepare_maps | §3 | FLUID |
| Manifest tracked, generated data gitignored | §4 | LOCKED |
| Resolution order params → scene → latest | §5 | LOCKED |
| Version-per-clip editorial control (MA/WS) | §6 | LOCKED |
| Largest-polygon island filtering by default | §7 | FLUID |
| Deterministic + realtime both first-class | §8 | LOCKED |

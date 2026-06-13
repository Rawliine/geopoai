# W14 — Map data: full catalog discovery + historical sources + resolver

Branch: `agents/w14-catalog` · Depends on: W00.

## Goal
Kill manual link-hunting. The version manifest becomes a lockfile that
tooling writes; the whole Natural Earth catalog plus historical-border
catalogs become discoverable by command; a missing version auto-resolves
or fails with the nearest available alternatives.

## Allowlist
map_renderer/data_prep/ · map_renderer/resolver.py ·
map_renderer/tests/test_catalog.py (new) ·
map_renderer/docs/fragments/W14.md (new)

## Read first
data_prep/prepare_maps.py · data_prep/map_versions.json + map_aliases.json ·
resolver.py (auto-provisioning fallback path) · broll/lib/asset_wrapper.py
(provenance philosophy to mirror)

## Checklist

### T1 — Catalog plugin interface
`data_prep/catalogs/__init__.py`: a catalog = `list_datasets() ->
[DatasetInfo]` + `manifest_entry(dataset) -> dict` (URL, format, license,
processing recipe). `prepare_maps.py --discover <catalog>` lists;
`--add <catalog>:<dataset>` writes the manifest entry + downloads;
`--add-all <catalog>` bulk-adds. Manifest entries gain mandatory fields:
`license`, `license_url`, `commercial_ok` (bool), `added_by` ("discover").
Existing hand-written entries: backfill license fields (Natural Earth = PD).

### T2 — Natural Earth catalog
`catalogs/natural_earth.py`: enumerate the NE vector catalog
programmatically (the nvkelso/natural-earth-vector GitHub repo tree, or the
NACIS CDN's predictable URL scheme — pick whichever is more stable, pin the
strategy in a comment). Cover at minimum the cultural family at 10/50/110m:
admin_0 countries / map_units / sovereignty / disputed_areas /
breakaway_disputed_areas / boundary_lines_land / admin_1 / populated_places.
populated_places gets a distinct processing recipe (point features →
`places.featurecollection.geojson` per version — needed for our own city
labels now that base labels are hidden).
Acceptance: `--discover natural_earth` lists ≥20 datasets; `--add` of
disputed_areas downloads and processes.

### T3 — Historical catalogs (license-gated)
- `catalogs/historical_basemaps.py`: index the aourednik/historical-basemaps
  GitHub repo (GeoJSON world borders by year). Dataset per year; version
  names like `world_1900`. READ THE REPO LICENSE during implementation and
  record it in `commercial_ok` honestly — if unclear, set false.
- `catalogs/cshapes.py`: CShapes 2.0 (1886–2019). Known research/
  non-commercial licensing — implement with `commercial_ok: false`.
- Resolver behavior for `commercial_ok: false`: load works but logs a
  prominent warning; `prepare_maps.py --audit` lists all non-commercial
  versions present locally.

### T4 — Year resolver
`resolver.py`: version strings that look like years (`"1942"`) resolve to
the nearest available historical dataset ≤ that year, with a logged note
(`1942 → world_1938 (nearest available)`). Exact-name resolution unchanged.

### T5 — Miss behavior
On unknown version: try discovery across registered catalogs for an exact
name match → auto-add + download on hit; on miss, raise with the 5 nearest
available version names (string distance + year proximity). The orchestrator
(W20) will rely on this error being machine-readable: raise a typed
exception carrying `suggestions: list[str]`.

### T6 — Tests
test_catalog.py: catalog listing (network-marked, skippable), manifest
entry shape, year resolution, miss-with-suggestions. Mock network where
practical.

### T7 — Docs fragment
`map_renderer/docs/fragments/W14.md`: --discover/--add/--add-all/--audit
usage, the catalog list, year-resolution behavior, commercial_ok semantics,
miss-with-suggestions behavior.

## Out of scope
Rendering changes · web/ anything · scene schema.

## Acceptance
`python -m map_renderer.data_prep.prepare_maps --discover natural_earth` and
`--add natural_earth:ne_10m_admin_0_disputed_areas --version disputed` work
end-to-end; a scene using `"version": "disputed"` renders;
`pytest map_renderer/tests/test_catalog.py` green.

"""Country name / map version resolution for map scenes (used by runner)."""

from __future__ import annotations

import copy
import difflib
import json
import logging
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from map_renderer.data_prep.catalogs import (
    find_dataset_across_catalogs,
    get_catalog,
    load_manifest,
    merge_manifest_entry,
)
from map_renderer.data_prep.errors import MapVersionNotFoundError
from map_renderer.data_prep.prepare_maps import process_version

ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = ROOT / "data" / "maps"
_DATA_PREP_DIR = Path(__file__).resolve().parent / "data_prep"
VERSIONS_MANIFEST_PATH = _DATA_PREP_DIR / "map_versions.json"
ALIASES_PATH = _DATA_PREP_DIR / "map_aliases.json"

log = logging.getLogger("render_scene")


def _version_file(version: str) -> Path:
    return MAPS_DIR / version / "countries.featurecollection.geojson"


def _warn_non_commercial(version: str) -> None:
    """Log a prominent warning when loading a non-commercial map version."""
    manifest = load_manifest(VERSIONS_MANIFEST_PATH)
    entry = manifest.get(version)
    if not isinstance(entry, dict):
        return
    if entry.get("commercial_ok") is not False:
        return
    license_name = entry.get("license", "unknown")
    license_url = entry.get("license_url", "")
    log.warning(
        "NON-COMMERCIAL MAP DATA: version '%s' (license=%s) is not cleared for "
        "commercial use. See %s",
        version,
        license_name,
        license_url or "(no license_url)",
    )


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {"ceasefire": "1991_ceasefire"}
    raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k.strip().lower()] = v.strip()
    return out


def _resolve_version_alias(version: str) -> str:
    aliases = _load_aliases()
    key = (version or "latest").strip().lower() or "latest"
    return aliases.get(key, key)  # fall back to the key itself (already defaults to "latest")


def _resolve_year_string(version: str, manifest: dict[str, dict]) -> str | None:
    """Map a 4-digit year to the nearest world_YYYY manifest key <= that year."""
    if not re.fullmatch(r"\d{4}", version):
        return None
    target = int(version)
    candidates: list[tuple[int, str]] = []
    for key in manifest:
        match = re.fullmatch(r"world_(\d{4})", key)
        if not match:
            continue
        year = int(match.group(1))
        if year <= target:
            candidates.append((year, key))
    if not candidates:
        return None
    _year, best_key = max(candidates, key=lambda item: item[0])
    log.info("%s → %s (nearest available)", version, best_key)
    return best_key


def _nearest_version_suggestions(query: str, manifest: dict[str, dict], n: int = 5) -> list[str]:
    keys = list(manifest.keys())
    if not keys:
        return []

    def _score(key: str) -> float:
        ratio = difflib.SequenceMatcher(None, query.lower(), key.lower()).ratio()
        year_bonus = 0.0
        if re.fullmatch(r"\d{4}", query):
            match = re.fullmatch(r"world_(\d{4})", key)
            if match:
                diff = abs(int(query) - int(match.group(1)))
                year_bonus = max(0.0, 1.0 - diff / 2000.0)
        return ratio + year_bonus

    ranked = sorted(keys, key=_score, reverse=True)
    return ranked[:n]


def _try_discovery_auto_add(version: str) -> str | None:
    """Search registered catalogs for an exact dataset_id match and auto-add."""
    hit = find_dataset_across_catalogs(version)
    if not hit:
        return None
    catalog_name, info = hit
    catalog = get_catalog(catalog_name)
    entry = dict(catalog.manifest_entry(info.dataset_id))
    entry.setdefault("added_by", "discover")
    merge_manifest_entry(VERSIONS_MANIFEST_PATH, version, entry)
    log.info(
        "Auto-discovered map version '%s' from catalog %s — downloading.",
        version,
        catalog_name,
    )
    process_version(VERSIONS_MANIFEST_PATH, version, quiet=True)
    return version


def _resolve_map_version(version: str) -> str:
    """Full version resolution: alias → year → manifest → discovery → miss."""
    raw = (version or "latest").strip() or "latest"
    resolved = _resolve_version_alias(raw)
    manifest = load_manifest(VERSIONS_MANIFEST_PATH)

    year_match = _resolve_year_string(resolved, manifest)
    if year_match:
        resolved = year_match

    if resolved in manifest:
        return resolved

    discovered = _try_discovery_auto_add(resolved)
    if discovered:
        return discovered

    suggestions = _nearest_version_suggestions(resolved, manifest, n=5)
    raise MapVersionNotFoundError(resolved, suggestions)


def _ensure_version_provisioned(version: str) -> str:
    """Download/process a manifest version if missing on disk."""
    if _version_file(version).exists():
        _warn_non_commercial(version)
        return version
    manifest = load_manifest(VERSIONS_MANIFEST_PATH)
    if version not in manifest:
        return version
    cmd = [
        sys.executable,
        str(ROOT / "config" / "prepare_maps.py"),
        "--from-manifest",
        "--manifest",
        str(VERSIONS_MANIFEST_PATH),
        "--version",
        version,
    ]
    log.info("Auto-provisioning map version '%s' via manifest.", version)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(
            "Auto-provision failed for version '%s': %s",
            version,
            result.stderr[-500:],
        )
    if _version_file(version).exists():
        _warn_non_commercial(version)
    return version


def _ensure_version_available(version: str) -> str:
    resolved = _resolve_map_version(version)
    return _ensure_version_provisioned(resolved)


def _normalize_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "on"}:
            return True
        if v in {"false", "0", "no", "off"}:
            return False
    return default


def _ring_area(ring: list[list[float]]) -> float:
    if len(ring) < 3:
        return 0.0
    area = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % len(ring)][0], ring[(i + 1) % len(ring)][1]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _feature_area(feat: dict) -> float:
    """Rough area of a feature's geometry (in geographic degrees²) for lookup ranking."""
    geom = feat.get("geometry") or {}
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        return _ring_area(coords[0]) if coords else 0.0
    if gtype == "MultiPolygon":
        return sum(_ring_area(poly[0]) for poly in coords if poly)
    return 0.0


def _maybe_filter_islands(feature: dict, include_islands: bool) -> dict:
    if include_islands:
        return feature
    geom = feature.get("geometry", {})
    if geom.get("type") != "MultiPolygon":
        return feature
    coords = geom.get("coordinates", [])
    if not coords:
        return feature
    largest = max(coords, key=lambda poly: _ring_area(poly[0]) if poly else 0.0)
    out = copy.deepcopy(feature)
    out["geometry"] = {"type": "Polygon", "coordinates": largest}
    return out


@lru_cache(maxsize=16)
def _load_country_lookup(version: str) -> tuple[dict[str, dict], str]:
    """Load lookup for requested version; fallback to latest only for known manifest keys."""
    raw = (version or "latest").strip() or "latest"
    requested = _resolve_map_version(raw)
    _ensure_version_provisioned(requested)
    chosen = requested
    path = _version_file(chosen)
    manifest = load_manifest(VERSIONS_MANIFEST_PATH)

    if not path.exists():
        if chosen in manifest:
            fallback = _version_file("latest")
            if not fallback.exists():
                raise FileNotFoundError(
                    f"Country dataset missing for version '{requested}' and fallback latest at {fallback}. "
                    "Run: python config/prepare_maps.py --from-manifest --version latest"
                )
            log.warning(
                "Map version '%s' provision failed, falling back to 'latest'.",
                requested,
            )
            chosen = "latest"
            path = fallback
        else:
            suggestions = _nearest_version_suggestions(requested, manifest, n=5)
            raise MapVersionNotFoundError(requested, suggestions)

    _LOOKUP_KEYS = ("ADMIN", "NAME", "SOVEREIGNT", "ISO_A3", "ADM0_A3",
                    "shapeName", "boundaryName", "name")

    def _index_feature(feat: dict, lkp: dict) -> None:
        props = feat.get("properties", {})
        for key in _LOOKUP_KEYS:
            val = props.get(key)
            if isinstance(val, str) and val.strip():
                k = val.strip().lower()
                if k not in lkp or _feature_area(feat) > _feature_area(lkp[k]):
                    lkp[k] = feat

    lookup: dict[str, dict] = {}
    _warn_non_commercial(chosen)
    countries_dir = MAPS_DIR / chosen / "countries"
    if countries_dir.exists() and any(countries_dir.glob("*.geojson")):
        # Fast path: read pre-extracted per-country files (avoids loading full FC)
        for f in countries_dir.glob("*.geojson"):
            try:
                feat = json.loads(f.read_text(encoding="utf-8"))
                _index_feature(feat, lookup)
            except Exception:
                pass
    else:
        # Slow path: parse full FeatureCollection
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError(
                f"Expected FeatureCollection in {path}, got {data.get('type')!r}"
            )
        for feat in data.get("features", []):
            _index_feature(feat, lookup)

    return lookup, chosen


def _resolve_scene_countries(scene: dict) -> dict:
    """
    Expand timeline actions with country references:
      params.country -> params.geojson
    Backwards-compatible: existing params.geojson is untouched.
    """
    timeline = scene.get("timeline", [])
    if not isinstance(timeline, list):
        return scene

    unresolved: list[str] = []
    used_versions: set[str] = set()
    scene_version = str(scene.get("_map_version", "latest"))
    scene_include_islands = _normalize_bool(scene.get("_include_islands", False), default=False)

    for i, entry in enumerate(timeline):
        if not isinstance(entry, dict):
            continue
        if entry.get("action") not in {"applyFill", "applyBorder"}:
            continue
        params = entry.get("params")
        if not isinstance(params, dict):
            continue
        if params.get("geojson"):
            continue
        country = params.get("country")
        if not isinstance(country, str) or not country.strip():
            continue
        action_version = str(params.get("version", scene_version))
        include_islands = _normalize_bool(params.get("include_islands", scene_include_islands), default=scene_include_islands)
        lookup, chosen_version = _load_country_lookup(action_version)
        used_versions.add(chosen_version)
        feat = lookup.get(country.strip().lower())
        if not feat:
            unresolved.append(
                f"timeline[{i}] id={params.get('id', '<no-id>')} country={country!r} version={action_version!r}"
            )
            continue
        params["geojson"] = _maybe_filter_islands(feat, include_islands)

    if unresolved:
        raise ValueError(
            "Unresolved country references:\n- " + "\n- ".join(unresolved)
        )
    if used_versions:
        log.info(
            "Country resolver: scene_version=%s scene_include_islands=%s versions_used=%s",
            scene_version,
            scene_include_islands,
            ",".join(sorted(used_versions)),
        )
    return scene

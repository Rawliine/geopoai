"""Country name / map version resolution for map scenes (used by runner)."""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = ROOT / "data" / "maps"
_DATA_PREP_DIR = Path(__file__).resolve().parent / "data_prep"
VERSIONS_MANIFEST_PATH = _DATA_PREP_DIR / "map_versions.json"
ALIASES_PATH = _DATA_PREP_DIR / "map_aliases.json"

log = logging.getLogger("render_scene")


def _version_file(version: str) -> Path:
    return MAPS_DIR / version / "countries.featurecollection.geojson"


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


def _ensure_version_available(version: str) -> str:
    resolved = _resolve_version_alias(version)
    if _version_file(resolved).exists():
        return resolved
    if not VERSIONS_MANIFEST_PATH.exists():
        return resolved
    cmd = [
        sys.executable,
        str(ROOT / "config" / "prepare_maps.py"),
        "--from-manifest",
        "--manifest",
        str(VERSIONS_MANIFEST_PATH),
        "--version",
        resolved,
    ]
    log.info("Auto-provisioning map version '%s' via manifest.", resolved)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(
            "Auto-provision failed for version '%s': %s",
            resolved,
            result.stderr[-500:],
        )
    return resolved


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
    """Load lookup for requested version, fallback to latest if missing."""
    requested = _ensure_version_available((version or "latest").strip() or "latest")
    chosen = requested
    path = _version_file(chosen)
    if not path.exists():
        fallback = _version_file("latest")
        if not fallback.exists():
            raise FileNotFoundError(
                f"Country dataset missing for version '{requested}' and fallback latest at {fallback}. "
                "Run data/prepare_ne_countries.py first."
            )
        log.warning("Map version '%s' not found, falling back to 'latest'.", requested)
        chosen = "latest"
        path = fallback

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

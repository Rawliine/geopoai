"""Historical basemaps catalog — aourednik/historical-basemaps GeoJSON by year.

License (read during W14 implementation): the repository LICENSE is GPL-3.0.
GeoJSON data-license terms remain ambiguous (see GitHub issue #74). We record
gpl-3.0 honestly and set commercial_ok=false because GPL copyleft and unclear
data terms make commercial reuse unsafe without legal review.
"""

from __future__ import annotations

import json
import re
import urllib.request
from functools import lru_cache

from map_renderer.data_prep.catalogs import DatasetInfo, register_catalog

CATALOG_NAME = "historical_basemaps"
_REPO = "aourednik/historical-basemaps"
_BRANCH = "master"
_RAW_BASE = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}"
_GITHUB_TREE_API = (
    f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
)

_LICENSE = "gpl-3.0"
_LICENSE_URL = f"https://github.com/{_REPO}/blob/{_BRANCH}/LICENSE"


@lru_cache(maxsize=1)
def _fetch_world_geojson_paths() -> list[str]:
    req = urllib.request.Request(
        _GITHUB_TREE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "GeoPoAI-map-catalog/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    paths: list[str] = []
    for item in data.get("tree", []):
        path = item.get("path", "")
        if re.fullmatch(r"geojson/world_.+\.geojson", path):
            paths.append(path)
    paths.sort()
    if not paths:
        raise RuntimeError(f"No world_*.geojson datasets found in {_REPO}")
    return paths


def _dataset_id_from_path(path: str) -> str:
    from pathlib import Path
    return Path(path).stem


def _year_label(dataset_id: str) -> str:
    # world_1900 → 1900; world_bc4000 → bc4000
    return dataset_id.removeprefix("world_")


def list_datasets() -> list[DatasetInfo]:
    out: list[DatasetInfo] = []
    for path in _fetch_world_geojson_paths():
        ds_id = _dataset_id_from_path(path)
        year = _year_label(ds_id)
        out.append(
            DatasetInfo(
                catalog=CATALOG_NAME,
                dataset_id=ds_id,
                resolution="vector",
                family="historical",
                description=f"World borders circa {year} (historical-basemaps)",
            )
        )
    return out


def manifest_entry(dataset_id: str) -> dict:
    valid = {d.dataset_id: d for d in list_datasets()}
    if dataset_id not in valid:
        raise KeyError(
            f"Unknown historical-basemaps dataset '{dataset_id}'. "
            f"Use --discover {CATALOG_NAME} to list available datasets."
        )
    info = valid[dataset_id]
    year = _year_label(dataset_id)
    return {
        "source_type": "geojson_url",
        "url": f"{_RAW_BASE}/geojson/{dataset_id}.geojson",
        "source_dataset": dataset_id,
        "resolution": "vector",
        "description": f"Historical basemaps world borders circa {year}",
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "commercial_ok": False,
        "added_by": "discover",
        "processing": "countries",
    }


class HistoricalBasemapsCatalog:
    name = CATALOG_NAME

    list_datasets = staticmethod(list_datasets)
    manifest_entry = staticmethod(manifest_entry)


register_catalog(HistoricalBasemapsCatalog())

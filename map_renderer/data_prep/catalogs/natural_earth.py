"""Natural Earth vector catalog — programmatic enumeration via NACIS CDN.

Strategy (pinned): use the NACIS S3 CDN predictable URL scheme rather than
scraping the nvkelso/natural-earth-vector GitHub tree. CDN paths are stable:

    https://naturalearth.s3.amazonaws.com/{resolution}_cultural/{dataset_id}.zip

Natural Earth data is public domain (see naturalearthdata.com terms).
"""

from __future__ import annotations

from map_renderer.data_prep.catalogs import DatasetInfo, register_catalog

CATALOG_NAME = "natural_earth"

# NACIS CDN base — pinned strategy (see module docstring).
_CDN = "https://naturalearth.s3.amazonaws.com"

RESOLUTIONS = ("10m", "50m", "110m")

# Cultural admin families required by W14 (8 families × 3 resolutions = 24 datasets).
_DATASET_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("admin_0_countries", "admin_0", "Sovereign country polygons (merged Morocco/Western Sahara)"),
    ("admin_0_map_units", "admin_0", "Map unit polygons (separate Morocco/Western Sahara)"),
    ("admin_0_sovereignty", "admin_0", "Sovereign vs dependent territory polygons"),
    ("admin_0_disputed_areas", "admin_0", "Disputed area polygons"),
    ("admin_0_breakaway_disputed_areas", "admin_0", "Breakaway and disputed area polygons"),
    ("admin_0_boundary_lines_land", "admin_0", "Land boundary lines"),
    ("admin_1_states_provinces", "admin_1", "First-level admin boundaries (states/provinces)"),
    ("populated_places", "places", "Populated places point features"),
)

_LICENSE = "pd"
_LICENSE_URL = "https://www.naturalearthdata.com/about/terms-of-use/"


def _dataset_id(resolution: str, family_suffix: str) -> str:
    return f"ne_{resolution}_{family_suffix}"


def _zip_url(resolution: str, dataset_id: str) -> str:
    return f"{_CDN}/{resolution}_cultural/{dataset_id}.zip"


def list_datasets() -> list[DatasetInfo]:
    out: list[DatasetInfo] = []
    for resolution in RESOLUTIONS:
        for family_suffix, family, description in _DATASET_FAMILIES:
            ds_id = _dataset_id(resolution, family_suffix)
            out.append(
                DatasetInfo(
                    catalog=CATALOG_NAME,
                    dataset_id=ds_id,
                    resolution=resolution,
                    family=family,
                    description=description,
                )
            )
    return out


def manifest_entry(dataset_id: str) -> dict:
    info_by_id = {d.dataset_id: d for d in list_datasets()}
    if dataset_id not in info_by_id:
        raise KeyError(
            f"Unknown Natural Earth dataset '{dataset_id}'. "
            f"Use --discover {CATALOG_NAME} to list available datasets."
        )
    info = info_by_id[dataset_id]
    processing = "places" if info.family == "places" else "countries"
    return {
        "source_type": "zip_url",
        "url": _zip_url(info.resolution, info.dataset_id),
        "source_dataset": info.dataset_id,
        "resolution": info.resolution,
        "description": f"Natural Earth {info.resolution} {info.description}",
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "commercial_ok": True,
        "added_by": "discover",
        "processing": processing,
    }


class NaturalEarthCatalog:
    name = CATALOG_NAME

    list_datasets = staticmethod(list_datasets)
    manifest_entry = staticmethod(manifest_entry)


register_catalog(NaturalEarthCatalog())

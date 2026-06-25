"""CShapes 2.0 catalog — global borders 1886–2019 (ETH Zurich).

License (read during W14 implementation): CC BY-NC-SA 4.0 — academic and
non-commercial use only. commercial_ok is false per W14 spec.
"""

from __future__ import annotations

from map_renderer.data_prep.catalogs import DatasetInfo, register_catalog

CATALOG_NAME = "cshapes"

_DATASET_ID = "cshapes_2_0"
_URL = "https://icr.ethz.ch/data/cshapes/CShapes-2.0.geojson"
_LICENSE = "cc-by-nc-sa-4.0"
_LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"


def list_datasets() -> list[DatasetInfo]:
    return [
        DatasetInfo(
            catalog=CATALOG_NAME,
            dataset_id=_DATASET_ID,
            resolution="vector",
            family="historical",
            description="CShapes 2.0 global state borders and capitals (1886–2019)",
        )
    ]


def manifest_entry(dataset_id: str) -> dict:
    if dataset_id != _DATASET_ID:
        raise KeyError(
            f"Unknown CShapes dataset '{dataset_id}'. "
            f"Use --discover {CATALOG_NAME} to list available datasets."
        )
    return {
        "source_type": "geojson_url",
        "url": _URL,
        "source_dataset": _DATASET_ID,
        "resolution": "vector",
        "description": "CShapes 2.0 global borders and capitals (1886–2019)",
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "commercial_ok": False,
        "added_by": "discover",
        "processing": "countries",
    }


class CShapesCatalog:
    name = CATALOG_NAME

    list_datasets = staticmethod(list_datasets)
    manifest_entry = staticmethod(manifest_entry)


register_catalog(CShapesCatalog())

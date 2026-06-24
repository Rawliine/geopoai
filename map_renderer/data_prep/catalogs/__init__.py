"""Map dataset catalog plugins — discoverable sources for map_versions.json."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MANIFEST_REQUIRED_FIELDS = frozenset({
    "source_type",
    "url",
    "source_dataset",
    "license",
    "license_url",
    "commercial_ok",
    "added_by",
})

MANIFEST_OPTIONAL_FIELDS = frozenset({
    "resolution",
    "description",
    "processing",
    "path",
})


@dataclass(frozen=True)
class DatasetInfo:
    """One discoverable dataset from a catalog."""

    catalog: str
    dataset_id: str
    resolution: str
    family: str
    description: str


class Catalog(Protocol):
    """Catalog plugin contract."""

    name: str

    def list_datasets(self) -> list[DatasetInfo]: ...

    def manifest_entry(self, dataset_id: str) -> dict[str, Any]: ...


_CATALOG_REGISTRY: dict[str, Catalog] = {}


def register_catalog(catalog: Catalog) -> None:
    _CATALOG_REGISTRY[catalog.name] = catalog


def get_catalog(name: str) -> Catalog:
    if name not in _CATALOG_REGISTRY:
        available = ", ".join(sorted(_CATALOG_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown catalog '{name}'. Available: {available}")
    return _CATALOG_REGISTRY[name]


def list_catalog_names() -> list[str]:
    return sorted(_CATALOG_REGISTRY)


def iter_catalogs() -> list[Catalog]:
    return [get_catalog(n) for n in list_catalog_names()]


def validate_manifest_entry(entry: dict[str, Any]) -> None:
    """Ensure a manifest value has mandatory provenance fields."""
    missing = MANIFEST_REQUIRED_FIELDS - set(entry)
    if missing:
        raise ValueError(f"Manifest entry missing required fields: {sorted(missing)}")
    if not isinstance(entry.get("commercial_ok"), bool):
        raise ValueError("Manifest entry 'commercial_ok' must be a bool")
    processing = entry.get("processing", "countries")
    if processing not in {"countries", "places"}:
        raise ValueError(f"Unsupported processing recipe: {processing!r}")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")
    return data


def write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    """Write manifest lockfile atomically (temp + replace)."""
    for key, entry in manifest.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry for '{key}' must be an object")
        validate_manifest_entry(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp"
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def merge_manifest_entry(
    path: Path,
    version_key: str,
    entry: dict[str, Any],
) -> None:
    """Add or update one version in the manifest lockfile."""
    validate_manifest_entry(entry)
    manifest = load_manifest(path)
    manifest[version_key] = entry
    write_manifest_atomic(path, manifest)


def find_dataset_across_catalogs(dataset_id: str) -> tuple[str, DatasetInfo] | None:
    """Return (catalog_name, info) for an exact dataset_id match."""
    target = dataset_id.strip()
    for catalog_name in list_catalog_names():
        catalog = get_catalog(catalog_name)
        for info in catalog.list_datasets():
            if info.dataset_id == target:
                return catalog_name, info
    return None

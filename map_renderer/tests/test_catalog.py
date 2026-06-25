"""Tests for W14 map catalog discovery and version resolver."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from map_renderer.data_prep.catalogs import (
    MANIFEST_REQUIRED_FIELDS,
    load_manifest,
    merge_manifest_entry,
    validate_manifest_entry,
)
from map_renderer.data_prep.catalogs.natural_earth import (
    CATALOG_NAME as NE_CATALOG,
    list_datasets as ne_list_datasets,
    manifest_entry as ne_manifest_entry,
)
from map_renderer.data_prep.errors import MapVersionNotFoundError
from map_renderer import resolver as map_resolver

pytestmark = pytest.mark.usefixtures("clear_resolver_caches")


@pytest.fixture
def clear_resolver_caches():
    map_resolver._load_aliases.cache_clear()
    map_resolver._load_country_lookup.cache_clear()
    yield
    map_resolver._load_aliases.cache_clear()
    map_resolver._load_country_lookup.cache_clear()


def test_ne_manifest_entry_shape():
    entry = ne_manifest_entry("ne_10m_admin_0_disputed_areas")
    missing = MANIFEST_REQUIRED_FIELDS - set(entry)
    assert not missing, f"Missing fields: {missing}"
    assert entry["commercial_ok"] is True
    assert entry["license"] == "pd"
    assert entry["processing"] == "countries"


def test_ne_populated_places_processing_recipe():
    entry = ne_manifest_entry("ne_10m_populated_places")
    assert entry["processing"] == "places"


def test_ne_manifest_entry_unknown_raises():
    with pytest.raises(KeyError, match="Unknown Natural Earth"):
        ne_manifest_entry("ne_10m_not_a_real_dataset")


def test_merge_manifest_entry_validates(tmp_path: Path):
    manifest = tmp_path / "map_versions.json"
    entry = ne_manifest_entry("ne_10m_admin_0_countries")
    merge_manifest_entry(manifest, "test_ne", entry)
    data = load_manifest(manifest)
    assert "test_ne" in data
    assert data["test_ne"]["license"] == "pd"


def test_resolve_year_string_nearest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = {
        "world_1938": {"source_type": "geojson_url", "url": "http://x", "source_dataset": "w",
                       "license": "gpl-3.0", "license_url": "http://l", "commercial_ok": False,
                       "added_by": "discover"},
        "world_1945": {"source_type": "geojson_url", "url": "http://y", "source_dataset": "w",
                       "license": "gpl-3.0", "license_url": "http://l", "commercial_ok": False,
                       "added_by": "discover"},
    }
    result = map_resolver._resolve_year_string("1942", manifest)
    assert result == "world_1938"


def test_resolve_year_string_no_match():
    assert map_resolver._resolve_year_string("1942", {"latest": {}}) is None
    assert map_resolver._resolve_year_string("not-a-year", {"world_1900": {}}) is None


def test_nearest_version_suggestions():
    manifest = {
        "latest": {},
        "world_1938": {},
        "world_1945": {},
        "1991_ceasefire": {},
    }
    suggestions = map_resolver._nearest_version_suggestions("1942", manifest, n=5)
    assert len(suggestions) == 4
    assert "world_1938" in suggestions


def test_resolve_map_version_miss_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest_path = tmp_path / "map_versions.json"
    manifest_path.write_text(json.dumps({"latest": ne_manifest_entry("ne_10m_admin_0_countries")}))
    monkeypatch.setattr(map_resolver, "VERSIONS_MANIFEST_PATH", manifest_path)

    with pytest.raises(MapVersionNotFoundError) as exc_info:
        map_resolver._resolve_map_version("totally_unknown_version_xyz")

    err = exc_info.value
    assert err.version == "totally_unknown_version_xyz"
    assert len(err.suggestions) <= 5


def test_resolve_map_version_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    manifest_path = tmp_path / "map_versions.json"
    manifest_path.write_text(json.dumps({
        "1991_ceasefire": ne_manifest_entry("ne_10m_admin_0_map_units"),
    }))
    aliases_path = tmp_path / "map_aliases.json"
    aliases_path.write_text(json.dumps({"ceasefire": "1991_ceasefire"}))
    monkeypatch.setattr(map_resolver, "VERSIONS_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(map_resolver, "ALIASES_PATH", aliases_path)
    map_resolver._load_aliases.cache_clear()

    assert map_resolver._resolve_map_version("ceasefire") == "1991_ceasefire"


@mock.patch("map_renderer.resolver.process_version")
@mock.patch("map_renderer.resolver.merge_manifest_entry")
def test_try_discovery_auto_add(mock_merge, mock_process, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest_path = tmp_path / "map_versions.json"
    manifest_path.write_text("{}")
    monkeypatch.setattr(map_resolver, "VERSIONS_MANIFEST_PATH", manifest_path)

    result = map_resolver._try_discovery_auto_add("world_1900")
    assert result == "world_1900"
    mock_merge.assert_called_once()
    mock_process.assert_called_once()


@pytest.mark.network
def test_ne_list_datasets_count():
    if not os.environ.get("GEOPO_NETWORK_TESTS"):
        pytest.skip("Set GEOPO_NETWORK_TESTS=1 to run network catalog tests")
    datasets = ne_list_datasets()
    assert len(datasets) >= 20
    assert all(ds.catalog == NE_CATALOG for ds in datasets)


@pytest.mark.network
def test_discover_natural_earth_cli():
    if not os.environ.get("GEOPO_NETWORK_TESTS"):
        pytest.skip("Set GEOPO_NETWORK_TESTS=1 to run network catalog tests")
    from map_renderer.data_prep.prepare_maps import _cmd_discover
    assert _cmd_discover("natural_earth") == 0

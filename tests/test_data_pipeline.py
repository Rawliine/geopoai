"""Tests for the data pipeline: version resolution, country lookup, and scene resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from map_renderer.data_prep.prepare_maps import find_feature_by_country, _country_slug  # noqa: E402
import map_renderer.resolver as resolver  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_feature(admin: str, area_deg2: float = 1.0, extra: dict | None = None) -> dict:
    """Create a minimal GeoJSON Feature with a square polygon of the given area."""
    side = area_deg2 ** 0.5
    return {
        "type": "Feature",
        "properties": {"ADMIN": admin, **(extra or {})},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [side, 0], [side, side], [0, side], [0, 0]]],
        },
    }


SAMPLE_FC = {
    "type": "FeatureCollection",
    "features": [
        _make_feature("Morocco",         area_deg2=100.0),
        _make_feature("Algeria",         area_deg2=200.0),
        _make_feature("Western Sahara",  area_deg2=50.0),
        {
            "type": "Feature",
            "properties": {"shapeName": "Spain", "ISO_A3": "ESP"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]],
            },
        },
        # Duplicate name — smaller area should lose
        {
            "type": "Feature",
            "properties": {"ADMIN": "Morocco", "NAME": "Clipperton Island"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]],
            },
        },
    ],
}


# ── find_feature_by_country ───────────────────────────────────────────────────

def test_find_by_admin_exact():
    feat = find_feature_by_country(SAMPLE_FC, "Morocco")
    assert feat is not None
    assert feat["properties"]["ADMIN"] == "Morocco"


def test_find_by_admin_case_insensitive():
    feat = find_feature_by_country(SAMPLE_FC, "morocco")
    assert feat is not None


def test_find_by_shape_name():
    feat = find_feature_by_country(SAMPLE_FC, "Spain")
    assert feat is not None
    assert feat["properties"]["ISO_A3"] == "ESP"


def test_find_returns_none_for_unknown():
    feat = find_feature_by_country(SAMPLE_FC, "Atlantis")
    assert feat is None


def test_find_multiword_country():
    feat = find_feature_by_country(SAMPLE_FC, "Western Sahara")
    assert feat is not None


# ── _country_slug ─────────────────────────────────────────────────────────────

def test_slug_basic():
    assert _country_slug("Morocco") == "morocco"


def test_slug_spaces():
    assert _country_slug("Western Sahara") == "western_sahara"


def test_slug_apostrophe():
    assert _country_slug("Côte d'Ivoire") == "côte_divoire"


# ── Area-based ranking in lookup ──────────────────────────────────────────────

def test_lookup_keeps_larger_area(tmp_path):
    """When two features share the same ADMIN name, the one with larger area wins."""
    fc_path = tmp_path / "test.featurecollection.geojson"
    fc_path.write_text(json.dumps(SAMPLE_FC), encoding="utf-8")

    lookup = {}
    for feat in SAMPLE_FC["features"]:
        props = feat.get("properties", {})
        for key in ("ADMIN", "NAME", "shapeName"):
            val = props.get(key)
            if isinstance(val, str) and val.strip():
                k = val.strip().lower()
                from map_renderer.resolver import _feature_area
                if k not in lookup or _feature_area(feat) > _feature_area(lookup[k]):
                    lookup[k] = feat

    morocco = lookup.get("morocco")
    assert morocco is not None
    from map_renderer.resolver import _feature_area
    assert _feature_area(morocco) > 50   # should be the 100 deg² feature, not the tiny island


# ── Version alias resolution ──────────────────────────────────────────────────

def test_resolve_known_alias():
    with patch.object(resolver, "_load_aliases", return_value={"ceasefire": "1991_ceasefire", "cf": "1991_ceasefire"}):
        result = resolver._resolve_version_alias("ceasefire")
        assert result == "1991_ceasefire"


def test_resolve_unknown_key_returns_itself():
    with patch.object(resolver, "_load_aliases", return_value={}):
        result = resolver._resolve_version_alias("my_custom_version")
        assert result == "my_custom_version"


def test_resolve_empty_defaults_to_latest():
    with patch.object(resolver, "_load_aliases", return_value={}):
        result = resolver._resolve_version_alias("")
        assert result == "latest"


# ── _normalize_bool ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (True,    True),
    (False,   False),
    ("true",  True),
    ("1",     True),
    ("yes",   True),
    ("on",    True),
    ("false", False),
    ("0",     False),
    ("no",    False),
    ("off",   False),
    (None,    False),
    ("maybe", False),
])
def test_normalize_bool(value, expected):
    assert resolver._normalize_bool(value, default=False) == expected


# ── _resolve_scene_countries raises on missing country ────────────────────────

def test_resolve_raises_on_missing_country():
    scene = {
        "_map_version": "latest",
        "timeline": [
            {
                "at": 0,
                "action": "applyFill",
                "params": {"id": "atlantis-fill", "country": "Atlantis"},
            }
        ],
    }
    mock_lookup = ({"morocco": _make_feature("Morocco")}, "latest")

    with patch.object(resolver, "_load_country_lookup", return_value=mock_lookup):
        with pytest.raises(ValueError, match="Atlantis"):
            resolver._resolve_scene_countries(scene)


def test_resolve_succeeds_for_known_country():
    scene = {
        "_map_version": "latest",
        "timeline": [
            {
                "at": 0,
                "action": "applyFill",
                "params": {"id": "morocco-fill", "country": "Morocco"},
            }
        ],
    }
    mock_feat = _make_feature("Morocco")
    mock_lookup = ({"morocco": mock_feat}, "latest")

    with patch.object(resolver, "_load_country_lookup", return_value=mock_lookup):
        result = resolver._resolve_scene_countries(scene)

    params = result["timeline"][0]["params"]
    assert "geojson" in params
    assert params["geojson"]["properties"]["ADMIN"] == "Morocco"

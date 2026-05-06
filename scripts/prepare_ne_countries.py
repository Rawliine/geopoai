#!/usr/bin/env python3
"""
Prepare Natural Earth Admin-0 countries from a ZIP shapefile.

Outputs:
  - Canonical FeatureCollection with properties preserved
  - Per-country Feature files for target countries
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import shapefile  # pyshp


DEFAULT_TARGETS = ["Morocco", "Algeria", "Spain", "France"]


def extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def build_featurecollection(shp_path: Path) -> dict:
    reader = shapefile.Reader(str(shp_path))
    fields = [f[0] for f in reader.fields[1:]]  # skip deletion flag
    features = []
    for sr in reader.iterShapeRecords():
        props = dict(zip(fields, sr.record))
        geom = sr.shape.__geo_interface__
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": geom,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def find_feature_by_country(fc: dict, country_name: str) -> dict | None:
    keys = ("ADMIN", "NAME", "NAME_EN", "SOVEREIGNT")
    name_l = country_name.lower()
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        for k in keys:
            v = props.get(k)
            if isinstance(v, str) and v.lower() == name_l:
                return feat
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", required=True, help="Path to NE zip")
    parser.add_argument(
        "--out-fc",
        dest="out_fc",
        default="data/ne_10m_admin_0_countries.featurecollection.geojson",
        help="Output FeatureCollection geojson path",
    )
    parser.add_argument(
        "--countries-dir",
        dest="countries_dir",
        default="data/countries",
        help="Output directory for per-country features",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=DEFAULT_TARGETS,
        help="Country names to export (ADMIN/NAME match)",
    )
    args = parser.parse_args()

    zip_path = Path(args.zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip not found: {zip_path}")

    extract_dir = zip_path.parent / (zip_path.stem + "_extracted")
    extract_zip(zip_path, extract_dir)

    shp_candidates = sorted(extract_dir.glob("*.shp"))
    if not shp_candidates:
        raise FileNotFoundError(f"No .shp found in {extract_dir}")
    shp_path = shp_candidates[0]

    fc = build_featurecollection(shp_path)

    out_fc = Path(args.out_fc)
    out_fc.parent.mkdir(parents=True, exist_ok=True)
    out_fc.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    countries_dir = Path(args.countries_dir)
    countries_dir.mkdir(parents=True, exist_ok=True)
    missing = []
    for country in args.targets:
        feat = find_feature_by_country(fc, country)
        if not feat:
            missing.append(country)
            continue
        out_path = countries_dir / f"{country.lower().replace(' ', '_')}.geojson"
        out_path.write_text(json.dumps(feat, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote FeatureCollection: {out_fc}")
    print(f"Wrote country features to: {countries_dir}")
    if missing:
        print("Missing countries:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

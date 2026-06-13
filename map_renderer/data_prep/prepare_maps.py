#!/usr/bin/env python3
"""Prepare versioned country datasets for the renderer.

Usage:
    python config/prepare_maps.py --list-versions   # shim → this module
    python config/prepare_maps.py --from-manifest --version latest
    python config/prepare_maps.py --from-manifest --version 1991_ceasefire
    python config/prepare_maps.py --zip /path/to/file.zip --version my_version
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

import shapefile  # pyshp

ROOT      = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "data" / ".cache"
MAPS_DIR  = ROOT / "data" / "maps"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "map_versions.json"

log = logging.getLogger("prepare_maps")


# ── Download ──────────────────────────────────────────────────────────────────

def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
    downloaded = min(block_num * block_size, max(total_size, 1))
    pct = downloaded * 100 // max(total_size, 1)
    kb_done = downloaded // 1024
    kb_total = total_size // 1024 if total_size > 0 else "?"
    sys.stderr.write(f"\r  {pct:3d}%  {kb_done} / {kb_total} KB   ")
    sys.stderr.flush()
    if total_size > 0 and downloaded >= total_size:
        sys.stderr.write("\n")
        sys.stderr.flush()


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s → %s", url, dest)
    urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
    size = dest.stat().st_size
    if size < 4096:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download too small ({size} bytes) — likely a redirect or error page.\n"
            f"URL: {url}"
        )
    log.info("Downloaded %s (%d KB)", dest.name, size // 1024)
    return dest


# ── Shapefile / GeoJSON helpers ───────────────────────────────────────────────

def _extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def _build_featurecollection(shp_path: Path) -> dict:
    reader = shapefile.Reader(str(shp_path))
    fields = [f[0] for f in reader.fields[1:]]
    features = []
    for sr in reader.iterShapeRecords():
        props = dict(zip(fields, sr.record))
        geom = sr.shape.__geo_interface__
        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": features}


def _normalize_to_featurecollection(source_path: Path) -> dict:
    suffix = source_path.suffix.lower()
    if suffix == ".geojson":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError(f"GeoJSON at {source_path} is not a FeatureCollection.")
        return data
    if suffix == ".zip":
        extract_dir = source_path.parent / (source_path.stem + "_extracted")
        _extract_zip(source_path, extract_dir)
        shp_candidates = sorted(extract_dir.glob("*.shp"))
        if not shp_candidates:
            raise FileNotFoundError(f"No .shp found in {extract_dir}")
        return _build_featurecollection(shp_candidates[0])
    if suffix == ".shp":
        return _build_featurecollection(source_path)
    raise ValueError(f"Unsupported source file type: {source_path.suffix!r}")


def find_feature_by_country(fc: dict, country_name: str) -> dict | None:
    """Case-insensitive lookup across common property keys."""
    keys = ("ADMIN", "NAME", "NAME_EN", "SOVEREIGNT", "ISO_A3", "ADM0_A3",
            "shapeName", "boundaryName", "name")
    target = country_name.strip().lower()
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        for k in keys:
            v = props.get(k)
            if isinstance(v, str) and v.strip().lower() == target:
                return feat
    return None


def _country_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("'", "").replace("-", "_")


# ── Manifest / source resolution ─────────────────────────────────────────────

def _source_from_manifest(manifest_path: Path, version: str) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if version not in manifest:
        available = ", ".join(manifest.keys())
        raise KeyError(
            f"Version '{version}' not in {manifest_path}.\n"
            f"Available: {available}"
        )
    cfg = manifest[version]
    source_type = cfg.get("source_type")
    cache_key = version

    if source_type == "local_path":
        p = Path(cfg["path"])
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Manifest local_path not found: {p}")
        return p

    if source_type in ("zip_url", "geojson_url"):
        url = cfg.get("url", "")
        if not url:
            raise ValueError(f"Missing 'url' for version '{version}'")
        ext = ".zip" if source_type == "zip_url" else ".geojson"
        cached = CACHE_DIR / f"{cache_key}{ext}"
        if cached.exists():
            log.info("Using cached download: %s", cached)
            return cached
        return _download(url, cached)

    raise ValueError(f"Unsupported source_type {source_type!r} for version '{version}'")


# ── Country extraction ────────────────────────────────────────────────────────

def _extract_all_countries(fc: dict, countries_dir: Path) -> tuple[int, list[str]]:
    """Write every named feature to countries/{slug}.geojson. Returns (written, unnamed)."""
    written = 0
    unnamed = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        name = (
            props.get("ADMIN") or props.get("NAME") or
            props.get("shapeName") or props.get("boundaryName") or
            props.get("name") or ""
        ).strip()
        if not name:
            unnamed.append(str(props))
            continue
        slug = _country_slug(name)
        (countries_dir / f"{slug}.geojson").write_text(
            json.dumps(feat, ensure_ascii=False), encoding="utf-8"
        )
        written += 1
    return written, unnamed


def _extract_targeted_countries(
    fc: dict, countries_dir: Path, targets: list[str]
) -> list[str]:
    """Write specific countries; return list of missing ones."""
    missing = []
    for country in targets:
        feat = find_feature_by_country(fc, country)
        if feat is None:
            missing.append(country)
            continue
        slug = _country_slug(country)
        (countries_dir / f"{slug}.geojson").write_text(
            json.dumps(feat, ensure_ascii=False), encoding="utf-8"
        )
    return missing


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare versioned country GeoJSON datasets for the renderer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list-versions", action="store_true",
                        help="Print available versions from the manifest and exit.")
    parser.add_argument("--from-manifest", action="store_true",
                        help="Resolve source URL from the manifest.")
    parser.add_argument("--zip", default=None, metavar="PATH",
                        help="Source ZIP file path (alternative to --from-manifest).")
    parser.add_argument("--geojson", default=None, metavar="PATH",
                        help="Source FeatureCollection GeoJSON path.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), metavar="PATH",
                        help=f"Manifest JSON path (default: {DEFAULT_MANIFEST}).")
    parser.add_argument("--version", default="latest",
                        help="Version key / output folder name (default: latest).")
    parser.add_argument("--out-dir", default=None, metavar="PATH",
                        help="Override output directory root.")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even if cached output exists.")
    parser.add_argument("--targets", nargs="*", default=None, metavar="COUNTRY",
                        help="Specific countries to extract (default: all).")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-error output.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    manifest_path = Path(args.manifest)

    # ── --list-versions ────────────────────────────────────────────────────────
    if args.list_versions:
        if not manifest_path.exists():
            log.error("Manifest not found: %s", manifest_path)
            return 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"\nAvailable map versions ({manifest_path}):\n")
        for k, v in manifest.items():
            res  = v.get("resolution", "?")
            desc = v.get("description", "")
            print(f"  {k:<25s}  [{res}]  {desc}")
        print()
        return 0

    # ── Resolve source ─────────────────────────────────────────────────────────
    out_root = Path(args.out_dir) if args.out_dir else (MAPS_DIR / args.version)
    out_root.mkdir(parents=True, exist_ok=True)
    out_fc = out_root / "countries.featurecollection.geojson"

    if out_fc.exists() and not args.force:
        log.info("Using cached FeatureCollection: %s", out_fc)
        fc = json.loads(out_fc.read_text(encoding="utf-8"))
    else:
        if args.from_manifest:
            source_path = _source_from_manifest(manifest_path, args.version)
        elif args.geojson:
            source_path = Path(args.geojson)
        elif args.zip:
            source_path = Path(args.zip)
        else:
            parser.error("Provide one of: --from-manifest, --geojson, --zip")

        if not source_path.exists():
            log.error("Source not found: %s", source_path)
            return 1

        fc = _normalize_to_featurecollection(source_path)
        out_fc.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        log.info("Wrote FeatureCollection (%d features) → %s",
                 len(fc.get("features", [])), out_fc)

    # ── Extract country files ─────────────────────────────────────────────────
    countries_dir = out_root / "countries"
    if countries_dir.exists() and args.force:
        shutil.rmtree(countries_dir)
    countries_dir.mkdir(parents=True, exist_ok=True)

    if args.targets:
        targets_list = [t for t in args.targets if t.strip()]
        missing = _extract_targeted_countries(fc, countries_dir, targets_list)
        written = len(targets_list) - len(missing)
        if missing:
            log.error("Countries not found in dataset: %s", ", ".join(missing))
            return 1
    else:
        written, unnamed = _extract_all_countries(fc, countries_dir)
        if unnamed:
            log.warning("%d features had no recognisable name and were skipped.", len(unnamed))

    log.info("Wrote %d country files → %s", written, countries_dir)
    if not args.quiet:
        print(f"✓  {args.version}: {written} countries → {out_root}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

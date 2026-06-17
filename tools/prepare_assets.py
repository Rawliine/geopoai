#!/usr/bin/env python3
"""Provision blessed asset packs into assets/ with manifest lockfile semantics."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from assets.catalog import PACKS, PackDefinition, ResolvedSource, list_pack_names, pack_slug  # noqa: E402

_MANIFEST_PATH = _ROOT / "assets" / "manifest.json"
_CACHE_DIR = _ROOT / "data" / ".cache" / "assets"
_ASSETS_ROOT = _ROOT / "assets"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict[str, Any]:
    if _MANIFEST_PATH.is_file():
        return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "packs": {}}


def _save_manifest(manifest: dict[str, Any]) -> None:
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "GeoPoAI-prepare-assets/1.0"})
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def _glob_match(name: str, pattern: str) -> bool:
    if "{" in pattern and "}" in pattern:
        base, rest = pattern.split("{", 1)
        options, tail = rest.split("}", 1)
        return any(_glob_match(name, f"{base}{opt}{tail}") for opt in options.split(","))
    if "**/" in pattern:
        _, tail = pattern.split("**/", 1)
        return fnmatch.fnmatch(name, tail) or fnmatch.fnmatch(Path(name).name, tail)
    return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(Path(name).name, pattern)


def _extract_members(
    archive_bytes: bytes,
    source: ResolvedSource,
) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(BytesIO(archive_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if source.archive_prefix and not name.startswith(source.archive_prefix):
                continue
            rel = name[len(source.archive_prefix) :] if source.archive_prefix else name
            if not rel or rel.endswith("/"):
                continue
            if not _glob_match(rel, source.extract_glob):
                continue
            if source.dest_subdir:
                rel = f"{source.dest_subdir}/{rel}"
            out[rel.lstrip("/")] = zf.read(info)
    return out


def _install_files(kind: str, pack_name: str, files: dict[str, bytes]) -> list[dict[str, str]]:
    slug = pack_slug(pack_name)
    dest_root = _ASSETS_ROOT / kind / slug
    manifest_files: list[dict[str, str]] = []
    for rel, content in sorted(files.items()):
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        digest = _sha256_bytes(content)
        manifest_files.append(
            {
                "path": str(dest.relative_to(_ROOT)).replace("\\", "/"),
                "sha256": digest,
            }
        )
    return manifest_files


def _resolve_source(defn: PackDefinition, manifest: dict[str, Any]) -> ResolvedSource:
    slug = pack_slug(defn.name)
    existing = manifest.get("packs", {}).get(slug)
    if existing:
        return ResolvedSource(
            resolved_url=existing["resolved_url"],
            version=existing["version"],
            archive_prefix=existing.get("_archive_prefix", ""),
            extract_glob=existing.get("_extract_glob", "**/*"),
            dest_subdir=existing.get("_dest_subdir", ""),
        )
    return defn.resolve()


def add_pack(pack_name: str, *, refresh: bool = False) -> None:
    if pack_name not in PACKS:
        raise SystemExit(f"unknown pack: {pack_name!r}")
    defn = PACKS[pack_name]
    manifest = _load_manifest()
    slug = pack_slug(defn.name)

    if slug in manifest.get("packs", {}) and not refresh:
        source = _resolve_source(defn, manifest)
    else:
        source = defn.resolve()

    if not defn.license or not defn.license_url:
        raise SystemExit(f"pack {pack_name!r} missing license metadata — fail closed")

    print(f"fetching {pack_name} from {source.resolved_url}")
    archive_bytes = _download(source.resolved_url)
    archive_sha = _sha256_bytes(archive_bytes)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / slug / f"{archive_sha}.zip"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        cache_path.write_bytes(archive_bytes)

    extracted = _extract_members(archive_bytes, source)
    if not extracted:
        raise SystemExit(
            f"no files matched for pack {pack_name!r} "
            f"(prefix={source.archive_prefix!r}, glob={source.extract_glob!r})"
        )

    manifest_files = _install_files(defn.kind, defn.name, extracted)
    pack_entry = {
        "name": defn.name,
        "kind": defn.kind,
        "resolved_url": source.resolved_url,
        "version": source.version,
        "sha256": archive_sha,
        "license": defn.license,
        "license_url": defn.license_url,
        "files": manifest_files,
        "_archive_prefix": source.archive_prefix,
        "_extract_glob": source.extract_glob,
        "_dest_subdir": source.dest_subdir,
    }
    manifest.setdefault("packs", {})[slug] = pack_entry
    _save_manifest(manifest)
    print(f"installed {len(manifest_files)} files for {pack_name} -> assets/{defn.kind}/{slug}/")


def verify_pack(pack_name: str | None = None) -> int:
    manifest = _load_manifest()
    packs = manifest.get("packs", {})
    if not packs:
        print("manifest has no packs — run --add first", file=sys.stderr)
        return 1

    targets = [pack_slug(pack_name)] if pack_name else sorted(packs.keys())
    errors: list[str] = []

    for slug in targets:
        if slug not in packs:
            errors.append(f"pack not in manifest: {slug}")
            continue
        entry = packs[slug]
        if not entry.get("license"):
            errors.append(f"{slug}: missing license field")
        cache_glob = list((_CACHE_DIR / slug).glob("*.zip")) if (_CACHE_DIR / slug).exists() else []
        expected_sha = entry["sha256"]
        cache_hit = any(p.name == f"{expected_sha}.zip" for p in cache_glob)
        if not cache_hit:
            errors.append(f"{slug}: cached archive missing for sha256 {expected_sha}")
        for file_entry in entry.get("files", []):
            path = _ROOT / file_entry["path"]
            if not path.is_file():
                errors.append(f"{slug}: missing file {file_entry['path']}")
                continue
            digest = _sha256_file(path)
            if digest != file_entry["sha256"]:
                errors.append(
                    f"{slug}: hash mismatch for {file_entry['path']} "
                    f"(expected {file_entry['sha256']}, got {digest})"
                )

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"verified {len(targets)} pack(s)")
    return 0


def cmd_list() -> None:
    manifest = _load_manifest()
    installed = set(manifest.get("packs", {}).keys())
    for name in list_pack_names():
        defn = PACKS[name]
        slug = pack_slug(name)
        status = "installed" if slug in installed else "available"
        print(f"{name:22}  kind={defn.kind:6}  {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add", metavar="PACK", help="download and install a pack")
    parser.add_argument("--all", action="store_true", help="install every catalog pack")
    parser.add_argument("--verify", action="store_true", help="verify manifest hashes")
    parser.add_argument("--list", action="store_true", help="list catalog packs")
    parser.add_argument("--refresh", action="store_true", help="re-resolve URL even if pinned")
    args = parser.parse_args()

    if args.list:
        cmd_list()
        return 0
    if args.add:
        add_pack(args.add, refresh=args.refresh)
        return 0
    if args.all:
        for name in list_pack_names():
            add_pack(name, refresh=args.refresh)
        return 0
    if args.verify:
        return verify_pack(args.add if args.add else None)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

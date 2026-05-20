"""broll.lib.asset_wrapper — the single path to disk.

Hard rule (AGENT.md §1): no module in the codebase may write an asset to disk
or download a URL without going through this module. The wrapper produces both
the asset file and its companion ``<asset_path>.meta.json`` atomically, or it
leaves nothing behind.

Two entry points:

* :func:`download` — fetch a remote URL and finalize as an asset.
* :func:`finalize` — adopt a file that already exists on disk (e.g. a ComfyUI
  result on a shared volume) and tag it with provenance.

Both validate the resulting meta dict against
``broll/schema/asset_meta_schema.json`` before any file is committed to its
final name. If validation fails the temp files are removed and the call raises.

Atomicity strategy
------------------

We use the POSIX "write to sibling temp, fsync, rename" pattern. ``os.replace``
is atomic on the same filesystem on Linux. We always place the temp file in the
same directory as the target so the rename can't cross filesystems. Meta is
written *after* the asset so a partial run never leaves a meta pointing at a
missing file; if meta writing fails we delete the asset we just placed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - environment misconfig
    raise ImportError(
        "broll.lib.asset_wrapper requires `jsonschema` (already pinned in requirements.txt). "
        "Install with `pip install -r requirements.txt`."
    ) from exc

from .errors import AssetWrapperError, SchemaValidationError

log = logging.getLogger("broll.asset_wrapper")

# ── Paths ────────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_SCHEMA_PATH = _THIS_DIR.parent / "schema" / "asset_meta_schema.json"
_REPO_ROOT = _THIS_DIR.parent.parent

# Network knobs. Conservative; sources can override per call via download(timeout=…)
_DEFAULT_TIMEOUT_SEC = 60
_DEFAULT_USER_AGENT = "GeoPoAI-broll/0.1 (+https://github.com/) python-urllib"
_MAX_BYTES = 512 * 1024 * 1024  # 512 MiB hard cap; raise via download(max_bytes=...)


# ── Schema (loaded once) ─────────────────────────────────────────────────────
def _load_schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)


_SCHEMA = _load_schema()
_VALIDATOR = Draft202012Validator(_SCHEMA)


def validate_meta(meta: dict[str, Any]) -> None:
    """Raise SchemaValidationError if ``meta`` is not a valid asset meta.

    Aggregates every error in one message so callers see all problems at once.
    """
    errors = sorted(_VALIDATOR.iter_errors(meta), key=lambda e: list(e.path))
    if not errors:
        return
    details = "\n".join(
        f"  - {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    )
    raise SchemaValidationError(f"asset meta failed validation:\n{details}")


# ── Helpers ──────────────────────────────────────────────────────────────────
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_relative(p: Path) -> str:
    """Return a repo-relative path string when possible, else absolute.

    Schema accepts either, but consistency makes ``ls`` output cleaner.
    """
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def _meta_path_for(asset_path: Path) -> Path:
    """Return the companion meta path for an asset.

    ``foo/bar.mp4`` → ``foo/bar.mp4.meta.json``. We append rather than replace
    the extension so the asset filename is preserved verbatim and a directory
    listing groups asset+meta together.
    """
    return asset_path.with_name(asset_path.name + ".meta.json")


@contextmanager
def _atomic_writer(target: Path, *, mode: str = "wb") -> Iterator[Any]:
    """Yield a file handle at a sibling temp path; rename to target on close.

    On exception, removes the temp file and re-raises. Caller never sees a
    partially-written ``target``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, mode) as fp:
            yield fp
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _build_meta(
    *,
    shot_id: str,
    asset_path: Path,
    kind: str,
    source: dict[str, Any],
    license: dict[str, Any],
    verification: dict[str, Any] | None,
    ai_metadata: dict[str, Any] | None,
    modifications: list[str] | None,
) -> dict[str, Any]:
    """Assemble a meta dict and normalize defaults.

    Does NOT validate — callers do that after assembly so the wrapper can decide
    whether to keep or roll back the asset file based on the result.
    """
    if kind == "stock_video" and ai_metadata is not None:
        raise AssetWrapperError("stock_video assets must have ai_metadata=None")
    if kind in ("ai_video", "ai_image") and ai_metadata is None:
        raise AssetWrapperError(f"{kind} assets require ai_metadata")

    meta: dict[str, Any] = {
        "shot_id": shot_id,
        "asset_path": _repo_relative(asset_path),
        "kind": kind,
        "source": {
            **{"version": None, "fetched_at": _utc_now_iso()},
            **source,
        },
        "license": {
            **{"attribution_text": None, "license_url": None},
            **license,
        },
        "verification": verification,
        "ai_metadata": ai_metadata,
        "modifications": list(modifications or []),
        "schema_version": "1",
    }
    return meta


def _write_meta(asset_path: Path, meta: dict[str, Any]) -> Path:
    meta_path = _meta_path_for(asset_path)
    with _atomic_writer(meta_path, mode="wb") as fp:
        fp.write(json.dumps(meta, indent=2, sort_keys=False).encode("utf-8"))
    return meta_path


# ── Public API ───────────────────────────────────────────────────────────────
def download(
    url: str,
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    kind: str,
    source: dict[str, Any],
    license: dict[str, Any],
    verification: dict[str, Any] | None = None,
    ai_metadata: dict[str, Any] | None = None,
    modifications: list[str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SEC,
    max_bytes: int = _MAX_BYTES,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch ``url`` to ``target_path`` and write its ``.meta.json`` atomically.

    Parameters
    ----------
    url:
        HTTP(S) URL to fetch. The wrapper enforces ``http``/``https`` schemes.
    target_path:
        Final on-disk path for the asset (e.g. ``output/broll/<shot_id>.mp4``).
    shot_id, kind, source, license, verification, ai_metadata, modifications:
        Provenance fields. ``source.url`` defaults to the fetch URL if missing;
        ``source.fetched_at`` defaults to now.
    timeout:
        Per-request timeout in seconds. Defaults to 60s.
    max_bytes:
        Hard cap on download size; raises if exceeded. Defaults to 512 MiB.
    headers:
        Extra HTTP headers (e.g. ``Authorization``). The wrapper always sets
        ``User-Agent`` if the caller doesn't.

    Returns
    -------
    dict
        The validated meta dict that was just written.

    Raises
    ------
    AssetWrapperError
        Network failure, oversize download, unsupported scheme.
    SchemaValidationError
        Final meta dict failed schema validation. Asset file is removed.
    """
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise AssetWrapperError(f"unsupported URL scheme: {url!r}")

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    req_headers = {"User-Agent": _DEFAULT_USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)

    log.info("download shot_id=%s url=%s target=%s", shot_id, url, target)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with _atomic_writer(target, mode="wb") as out:
                written = 0
                chunk_size = 1 << 16
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise AssetWrapperError(
                            f"download exceeded max_bytes={max_bytes} for shot_id={shot_id}"
                        )
                    out.write(chunk)
    except urllib.error.URLError as exc:
        raise AssetWrapperError(f"download failed for {url}: {exc}") from exc

    # Source dict gets the actual fetch URL stamped in unless the caller already set one.
    source = dict(source)
    source.setdefault("url", url)

    meta = _build_meta(
        shot_id=shot_id,
        asset_path=target,
        kind=kind,
        source=source,
        license=license,
        verification=verification,
        ai_metadata=ai_metadata,
        modifications=modifications,
    )

    try:
        validate_meta(meta)
    except SchemaValidationError:
        # Roll back the asset; without a valid meta, the file is orphaned by definition.
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise

    _write_meta(target, meta)
    log.info("download OK shot_id=%s bytes=%d meta=%s", shot_id, written, _meta_path_for(target))
    return meta


def finalize(
    local_path: str | os.PathLike[str],
    target_path: str | os.PathLike[str],
    *,
    shot_id: str,
    kind: str,
    source: dict[str, Any],
    license: dict[str, Any],
    verification: dict[str, Any] | None = None,
    ai_metadata: dict[str, Any] | None = None,
    modifications: list[str] | None = None,
    move: bool = True,
) -> dict[str, Any]:
    """Adopt a file already on disk and tag it with provenance.

    Used by AI sources where ComfyUI has already written the result to a temp
    or shared path. Behaviour matches :func:`download` for everything except
    the byte-transfer step, which is replaced by a same-filesystem ``rename``
    (``move=True``, default) or a ``copy2`` (``move=False``).
    """
    local = Path(local_path)
    target = Path(target_path)
    if not local.exists():
        raise AssetWrapperError(f"finalize source missing: {local}")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Move/copy into a sibling tempfile of the target so the visible commit is
    # the same atomic rename as in download().
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        if move:
            shutil.move(str(local), str(tmp_path))
        else:
            shutil.copy2(str(local), str(tmp_path))
        os.replace(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    meta = _build_meta(
        shot_id=shot_id,
        asset_path=target,
        kind=kind,
        source=source,
        license=license,
        verification=verification,
        ai_metadata=ai_metadata,
        modifications=modifications,
    )
    try:
        validate_meta(meta)
    except SchemaValidationError:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise

    _write_meta(target, meta)
    log.info("finalize OK shot_id=%s meta=%s", shot_id, _meta_path_for(target))
    return meta


def load_meta(asset_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read and schema-validate the meta for an existing asset."""
    meta_path = _meta_path_for(Path(asset_path))
    if not meta_path.exists():
        raise AssetWrapperError(f"no meta found for asset: {asset_path} (expected {meta_path})")
    with meta_path.open("r", encoding="utf-8") as fp:
        meta = json.load(fp)
    validate_meta(meta)
    return meta


def meta_path_for(asset_path: str | os.PathLike[str]) -> Path:
    """Public version of the meta-path helper, for callers that want to check existence."""
    return _meta_path_for(Path(asset_path))

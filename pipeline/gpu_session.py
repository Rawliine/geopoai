#!/usr/bin/env python3
"""pipeline/gpu_session.py — Generic GPU session manager for Verda workloads.

Lifecycle: up → health → use → auto-down (via watchdog / budget caps).

`destroy instance` / `down` never touch verda_volume.models. `destroy volume` is a
separate, confirmed operator path (Verda API DELETE + terraform state rm).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INFRA_DIR = _REPO_ROOT / "infra"
_SESSIONS_PATH = _INFRA_DIR / "sessions.json"
_STATE_PATH = _INFRA_DIR / ".session_state.json"
_ENV_PATH = _REPO_ROOT / ".env"
_ENV_BAK_PATH = _REPO_ROOT / ".env.bak"

# Hardcoded — never parameterize; no code path may pass volume resources to destroy.
_DESTROY_TARGET = "verda_instance.this"

log = logging.getLogger("pipeline.gpu_session")


@dataclass(frozen=True)
class HealthSpec:
    type: str
    port: int | None = None
    path: str | None = None


@dataclass(frozen=True)
class GpuProfile:
    """Session profile — instance_type/use_spot from registry; verda_image from Verda catalog."""

    name: str
    instance_type: str
    use_spot: bool
    label: str
    location: str | None = None
    image_preference: tuple[str, ...] = ()
    verda_image: str = ""

    @property
    def gpu_type(self) -> str:
        return self.instance_type


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    tfvars: list[str]
    health: HealthSpec
    env_export: str | None
    default_gpu_profile: str
    gpu_preference: list[str]
    idle_minutes: int
    max_session_hours: int


@dataclass(frozen=True)
class StorageConfig:
    models_marker: str
    default_volume_size_gb: int
    volume_monthly_usd_per_gb: float


@dataclass(frozen=True)
class GpuOffering:
    location: str
    instance_type: str
    display_name: str
    vram_gb: float | None
    price_ondemand: float | None
    price_spot: float | None
    supported_os: tuple[str, ...]


@dataclass(frozen=True)
class VolumeState:
    id: str | None
    name: str | None
    location: str | None
    size_gb: int | None
    status: str | None
    monthly_cost_estimate: float | None
    in_terraform_state: bool


# Verda Public API — https://api.verda.com/v1/docs
#   GET  /instance-types              catalog (public; supported_os, price_per_hour, spot_price)
#   GET  /instance-availability       per-location free SKUs (OAuth)
#   GET  /instance-availability/{id}  boolean availability (OAuth)
#   GET  /volumes                     block volumes (OAuth)
#   DELETE /volumes/{id}              delete volume (OAuth)
#   POST /oauth2/token                client_credentials
_VERDA_API_BASE = os.environ.get("VERDA_BASE_URL", "https://api.verda.com/v1").rstrip("/")

# GeoPoAI terraform image preference — must be members of instance-types[].supported_os
# (see infra/README.md troubleshooting: match gpu_type to supported_os via GET /instance-types)
_DEFAULT_IMAGE_PREFERENCE: tuple[str, ...] = (
    "ubuntu-24.04-cuda-13.0-open-docker",
    "ubuntu-22.04-cuda-13.0-open-docker",
    "ubuntu-22.04-cuda-12.4-docker",
    "ubuntu-22.04-cuda-12.4",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_registry(
    path: Path = _SESSIONS_PATH,
) -> tuple[dict[str, float], dict[str, GpuProfile], dict[str, WorkloadSpec]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    gpu_rates = {
        str(k): float(v)
        for k, v in raw.get("gpu_hourly_usd", {}).items()
        if not str(k).startswith("_") and v is not None
    }
    gpu_profiles: dict[str, GpuProfile] = {}
    for name, entry in raw.get("gpu_profiles", {}).items():
        inst = str(entry.get("instance_type") or entry.get("gpu_type", ""))
        pref = tuple(entry.get("image_preference") or ())
        gpu_profiles[name] = GpuProfile(
            name=name,
            instance_type=inst,
            use_spot=bool(entry["use_spot"]),
            label=str(entry.get("label", name)),
            location=entry.get("location"),
            image_preference=pref,
        )
    workloads: dict[str, WorkloadSpec] = {}
    for name, entry in raw["workloads"].items():
        health_raw = entry["health"]
        preference = list(entry.get("gpu_preference") or [])
        workloads[name] = WorkloadSpec(
            name=name,
            tfvars=list(entry["tfvars"]),
            health=HealthSpec(
                type=health_raw["type"],
                port=health_raw.get("port"),
                path=health_raw.get("path"),
            ),
            env_export=entry.get("env_export"),
            default_gpu_profile=str(entry["default_gpu_profile"]),
            gpu_preference=preference,
            idle_minutes=int(entry["idle_minutes"]),
            max_session_hours=int(entry["max_session_hours"]),
        )
    return gpu_rates, gpu_profiles, workloads


def load_storage_config(path: Path = _SESSIONS_PATH) -> StorageConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    storage = raw.get("storage") or {}
    return StorageConfig(
        models_marker=str(storage.get("models_marker", "/mnt/models/.geopoai_download_complete")),
        default_volume_size_gb=int(storage.get("default_volume_size_gb", 280)),
        volume_monthly_usd_per_gb=float(storage.get("volume_monthly_usd_per_gb", 0.10)),
    )


def load_state(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = path or _STATE_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    path = path or _STATE_PATH
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_session(state: dict[str, dict[str, Any]], workload: str) -> dict[str, Any] | None:
    return state.get(workload)


def record_activity(workload: str, *, path: Path | None = None) -> None:
    """Update last_activity_at for a workload (file-touch fallback for idle watchdog)."""
    path = path or _STATE_PATH
    state = load_state(path)
    session = state.get(workload)
    if not session:
        return
    session["last_activity_at"] = _iso(_utc_now())
    save_state(state, path)


def _read_tfvar_string(tfvars_rel: str, key: str) -> str | None:
    path = _INFRA_DIR / tfvars_rel
    if not path.exists():
        return None
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"')
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if m:
            return m.group(1)
    return None


def _read_gpu_type_from_tfvars(tfvars_rel: str) -> str | None:
    return _read_tfvar_string(tfvars_rel, "gpu_type")


def resolve_workload_location(workload: WorkloadSpec, profile: GpuProfile | None = None) -> str:
    if profile and profile.location:
        return profile.location
    for tfvar in reversed(workload.tfvars):
        loc = _read_tfvar_string(tfvar, "location")
        if loc:
            return loc
    return "FIN-03"


def verda_oauth_token(*, api_base: str = _VERDA_API_BASE) -> str | None:
    """POST /oauth2/token (client_credentials). Returns None if creds missing/invalid."""
    _load_dotenv_into_environ()
    client_id = os.environ.get("VERDA_CLIENT_ID", "")
    client_secret = os.environ.get("VERDA_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None
    body = json.dumps(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(
        f"{api_base}/oauth2/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
        token = payload.get("access_token")
        return str(token) if token else None
    except urllib.error.HTTPError as exc:
        log.warning("Verda OAuth failed (%s): %s", exc.code, exc.read().decode(errors="replace")[:200])
        return None


def verda_api_get(path: str, *, token: str | None = None, api_base: str = _VERDA_API_BASE) -> Any:
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{api_base}/{path.lstrip('/')}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_verda_instance_types(*, api_base: str = _VERDA_API_BASE) -> list[dict[str, Any]]:
    """GET /instance-types — public catalog (Verda API docs: Instance Types)."""
    payload = verda_api_get("instance-types", api_base=api_base)
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected instance-types payload: {type(payload)}")
    return payload


def index_instance_types(types: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(t["instance_type"]): t for t in types if t.get("instance_type")}


def rates_from_catalog(types: list[dict[str, Any]]) -> dict[str, float]:
    """Build $/h lookup from Verda catalog spot_price / price_per_hour fields."""
    rates: dict[str, float] = {}
    for item in types:
        inst = str(item.get("instance_type", ""))
        if not inst:
            continue
        for key in ("price_per_hour", "spot_price"):
            raw = item.get(key)
            if raw is not None and str(raw).strip():
                try:
                    rates[inst] = float(raw)
                except ValueError:
                    pass
                break
    return rates


def resolve_verda_image(
    catalog_entry: dict[str, Any],
    image_preference: tuple[str, ...] = (),
) -> str:
    """Pick terraform `verda_image` from instance-types[].supported_os (Verda API)."""
    supported = [str(x) for x in (catalog_entry.get("supported_os") or [])]
    if not supported:
        raise ValueError(
            f"no supported_os for {catalog_entry.get('instance_type')}; "
            "check GET /v1/instance-types"
        )
    for candidate in image_preference or _DEFAULT_IMAGE_PREFERENCE:
        if candidate in supported:
            return candidate
    for candidate in supported:
        if candidate.startswith("ubuntu-") and "docker" in candidate:
            return candidate
    return supported[0]


def fetch_instance_availability_by_location(
    token: str,
    *,
    api_base: str = _VERDA_API_BASE,
) -> dict[str, set[str]]:
    """GET /instance-availability — location_code → set of free instance_type strings."""
    payload = verda_api_get("instance-availability", token=token, api_base=api_base)
    out: dict[str, set[str]] = {}
    if not isinstance(payload, list):
        return out
    for row in payload:
        code = str(row.get("location_code", ""))
        avail = row.get("availabilities") or []
        out[code] = {str(x) for x in avail}
    return out


def check_instance_type_available(
    instance_type: str,
    token: str,
    *,
    api_base: str = _VERDA_API_BASE,
) -> bool | None:
    """GET /instance-availability/{instance_type} → boolean; None if request fails."""
    try:
        payload = verda_api_get(
            f"instance-availability/{instance_type}",
            token=token,
            api_base=api_base,
        )
        return bool(payload)
    except urllib.error.HTTPError:
        return None


def resolve_profiles_for_location(
    chain: list[GpuProfile],
    catalog: dict[str, dict[str, Any]],
    location: str,
    availability: dict[str, set[str]] | None,
) -> list[GpuProfile]:
    """Filter preference chain using Verda availability; resolve verda_image from catalog."""
    loc_avail = availability.get(location) if availability else None
    resolved: list[GpuProfile] = []
    for profile in chain:
        entry = catalog.get(profile.instance_type)
        if not entry:
            log.warning(
                "profile %s: instance_type %s not in GET /instance-types catalog — skip",
                profile.name,
                profile.instance_type,
            )
            continue
        if loc_avail is not None and profile.instance_type not in loc_avail:
            log.info(
                "profile %s (%s): not in GET /instance-availability for %s — skip",
                profile.name,
                profile.instance_type,
                location,
            )
            continue
        try:
            image = resolve_verda_image(entry, profile.image_preference)
        except ValueError as exc:
            log.warning("%s", exc)
            continue
        resolved.append(
            GpuProfile(
                name=profile.name,
                instance_type=profile.instance_type,
                use_spot=profile.use_spot,
                label=profile.label,
                location=profile.location or location,
                image_preference=profile.image_preference,
                verda_image=image,
            )
        )
    return resolved


def is_service_unavailable(result: subprocess.CompletedProcess[str]) -> bool:
    """Verda API error code service_unavailable → HTTP 503 (api.verda.com/v1/docs)."""
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    lower = text.lower()
    if "service_unavailable" in lower:
        return True
    if '"code":"service_unavailable"' in lower.replace(" ", ""):
        return True
    if "503" in lower and "not enough resources" in lower:
        return True
    return False


def is_startup_script_immutable_error(result: subprocess.CompletedProcess[str]) -> bool:
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    return "startup scripts cannot be updated" in text.lower()


def is_definitive_apply_failure(result: subprocess.CompletedProcess[str]) -> bool:
    """Terraform/Verda errors where retrying the same profile cannot succeed."""
    if result.returncode == 0:
        return False
    if is_service_unavailable(result):
        return False
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    lower = text.lower()
    markers = (
        "startup scripts cannot be updated",
        "volumes not found",
        "instance cannot be destroyed",
        "error:",
        "client error",
    )
    return any(m in lower for m in markers)


def resolve_gpu_type(workload: WorkloadSpec, profile: GpuProfile | None = None) -> str:
    if profile:
        return profile.gpu_type
    for tfvar in workload.tfvars:
        gpu = _read_gpu_type_from_tfvars(tfvar)
        if gpu:
            return gpu
    return workload.default_gpu_profile


def profile_for_session(
    session: dict[str, Any],
    gpu_profiles: dict[str, GpuProfile],
) -> GpuProfile | None:
    name = session.get("gpu_profile")
    if name and name in gpu_profiles:
        base = gpu_profiles[name]
        image = session.get("verda_image") or base.verda_image
        instance_type = session.get("gpu_type") or base.instance_type
        return GpuProfile(
            name=base.name,
            instance_type=str(instance_type),
            use_spot=bool(session.get("use_spot", base.use_spot)),
            label=base.label,
            location=session.get("location") or base.location,
            image_preference=base.image_preference,
            verda_image=str(image),
        )
    gpu_type = session.get("gpu_type")
    verda_image = session.get("verda_image")
    if gpu_type and verda_image:
        return GpuProfile(
            name="session",
            instance_type=str(gpu_type),
            use_spot=bool(session.get("use_spot", False)),
            label="restored from session state",
            verda_image=str(verda_image),
        )
    return None


def profiles_to_try(
    workload: WorkloadSpec,
    gpu_profiles: dict[str, GpuProfile],
    *,
    force_profile: str | None = None,
) -> list[GpuProfile]:
    if force_profile:
        if force_profile not in gpu_profiles:
            raise ValueError(f"unknown gpu profile: {force_profile}")
        return [gpu_profiles[force_profile]]
    chain: list[GpuProfile] = []
    for name in workload.gpu_preference:
        if name in gpu_profiles:
            chain.append(gpu_profiles[name])
    if not chain:
        raise ValueError(f"workload {workload.name} has no gpu_preference profiles in registry")
    return chain


def is_capacity_error(result: subprocess.CompletedProcess[str]) -> bool:
    """Alias for tests — Verda documents this as service_unavailable (503)."""
    return is_service_unavailable(result)


def format_gpu_catalog(
    types: list[dict[str, Any]],
    *,
    spot: bool = False,
    availability: dict[str, set[str]] | None = None,
    location: str | None = None,
) -> str:
    rows: list[tuple[str, str, str, str, str, str]] = []
    loc_set = availability.get(location) if availability and location else None
    for item in types:
        inst = str(item.get("instance_type", ""))
        if not inst:
            continue
        name = str(item.get("display_name") or item.get("name", inst))
        price_key = "spot_price" if spot else "price_per_hour"
        price = str(item.get(price_key, "?"))
        vram = str(item.get("gpu_memory", {}).get("size_in_gigabytes", "?"))
        if loc_set is None:
            avail = "?"
        else:
            avail = "yes" if inst in loc_set else "no"
        rows.append((inst, name[:28], f"${price}", f"{vram}GB", avail, inst))
    rows.sort(key=lambda r: float(r[2].lstrip("$") or 0))
    loc_note = f" @ {location}" if location else ""
    header = f"{'instance_type':<18} {'name':<28} {'$/h':>8} {'vram':>6} {'free':>4}"
    lines = [header, "-" * len(header)]
    lines.extend(
        f"{inst:<18} {name:<28} {price:>8} {vram:>6} {avail:>4}"
        for inst, name, price, vram, avail, _ in rows
    )
    mode = "spot" if spot else "on-demand"
    src = "GET /v1/instance-types"
    if availability is not None:
        src += " + GET /v1/instance-availability"
    return f"Verda GPU catalog ({mode}{loc_note}, {len(rows)} SKUs; {src})\n" + "\n".join(lines)


def _float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vram_gb_from_catalog(item: dict[str, Any]) -> float | None:
    gpu_mem = item.get("gpu_memory") or {}
    raw = gpu_mem.get("size_in_gigabytes")
    return _float_or_none(raw)


def build_gpu_offerings(
    catalog: list[dict[str, Any]],
    availability: dict[str, set[str]],
    *,
    include_cpu: bool = False,
    location_filter: str | None = None,
    sort_by: str = "ondemand",
) -> list[GpuOffering]:
    """Flat list of free SKUs across locations (W23 browse table)."""
    indexed = index_instance_types(catalog)
    rows: list[GpuOffering] = []
    for loc, free_types in sorted(availability.items()):
        if location_filter and loc != location_filter:
            continue
        for inst in sorted(free_types):
            if not include_cpu and inst.startswith("CPU."):
                continue
            entry = indexed.get(inst)
            if not entry:
                continue
            rows.append(
                GpuOffering(
                    location=loc,
                    instance_type=inst,
                    display_name=str(entry.get("display_name") or entry.get("name", inst))[:40],
                    vram_gb=_vram_gb_from_catalog(entry),
                    price_ondemand=_float_or_none(entry.get("price_per_hour")),
                    price_spot=_float_or_none(entry.get("spot_price")),
                    supported_os=tuple(str(x) for x in (entry.get("supported_os") or [])),
                )
            )

    def sort_key(row: GpuOffering) -> tuple[float, float, str]:
        if sort_by == "spot":
            price = row.price_spot if row.price_spot is not None else 1e9
        elif sort_by == "vram":
            return (0.0, -(row.vram_gb or 0.0), row.instance_type)
        else:
            price = row.price_ondemand if row.price_ondemand is not None else 1e9
        return (price, -(row.vram_gb or 0.0), row.instance_type)

    rows.sort(key=sort_key)
    return rows


def format_gpu_offerings_table(
    offerings: list[GpuOffering],
    *,
    title: str = "Available GPUs (free SKUs)",
) -> str:
    header = f"{'#':>3}  {'location':<8} {'instance_type':<20} {'vram':>6} {'$/h OD':>8} {'$/h spot':>9}  name"
    lines = [title, header, "-" * len(header)]
    for idx, row in enumerate(offerings, start=1):
        vram = f"{int(row.vram_gb)}GB" if row.vram_gb is not None else "?"
        pod = f"{row.price_ondemand:.2f}" if row.price_ondemand is not None else "?"
        psp = f"{row.price_spot:.2f}" if row.price_spot is not None else "?"
        lines.append(
            f"{idx:>3}  {row.location:<8} {row.instance_type:<20} {vram:>6} {pod:>8} {psp:>9}  {row.display_name}"
        )
    lines.append("")
    lines.append("Commands: number = pick | r = refresh | s = sort (ondemand/spot/vram) | q = quit")
    return "\n".join(lines)


def fetch_verda_volumes(token: str, *, api_base: str = _VERDA_API_BASE) -> list[dict[str, Any]]:
    """GET /volumes — block volumes (OAuth)."""
    payload = verda_api_get("volumes", token=token, api_base=api_base)
    if isinstance(payload, list):
        return payload
    return []


def verda_api_delete(path: str, *, token: str, api_base: str = _VERDA_API_BASE) -> None:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    req = urllib.request.Request(f"{api_base}/{path.lstrip('/')}", headers=headers, method="DELETE")
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"DELETE {path} unexpected status {resp.status}")


def _parse_terraform_state_show(resource: str) -> dict[str, str]:
    result = run_terraform(["state", "show", resource])
    if result.returncode != 0:
        return {}
    out: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"')
        out[key] = val
    return out


def instance_in_terraform_state() -> bool:
    result = run_terraform(["state", "list"])
    if result.returncode != 0:
        return False
    return any(line.strip() == "verda_instance.this" for line in (result.stdout or "").splitlines())


def read_volume_state(
    token: str | None = None,
    storage: StorageConfig | None = None,
) -> VolumeState:
    """Merge Terraform state for verda_volume.models with live Verda GET /volumes."""
    storage = storage or load_storage_config()
    tf = _parse_terraform_state_show("verda_volume.models")
    in_tf = bool(tf.get("id"))
    vol_id = tf.get("id")
    name = tf.get("name")
    location = tf.get("location") or None
    size_raw = tf.get("size")
    status = tf.get("status")
    size_gb = int(size_raw) if size_raw and size_raw.isdigit() else None

    if token:
        for vol in fetch_verda_volumes(token):
            vid = str(vol.get("id", ""))
            if vol_id and vid == vol_id:
                name = str(vol.get("name") or name or "")
                location = str(vol.get("location") or location or "") or None
                status = str(vol.get("status") or status or "")
                if vol.get("size") is not None:
                    try:
                        size_gb = int(vol.get("size"))
                    except (TypeError, ValueError):
                        pass
                break
            if not vol_id and name and str(vol.get("name", "")) == name:
                vol_id = vid
                location = str(vol.get("location") or "") or None
                status = str(vol.get("status") or "")
                break

    monthly = None
    if size_gb is not None:
        monthly = round(size_gb * storage.volume_monthly_usd_per_gb, 2)

    return VolumeState(
        id=vol_id,
        name=name,
        location=location,
        size_gb=size_gb,
        status=status,
        monthly_cost_estimate=monthly,
        in_terraform_state=in_tf,
    )


def offering_to_profile(offering: GpuOffering, *, use_spot: bool) -> GpuProfile:
    catalog_entry = {
        "instance_type": offering.instance_type,
        "supported_os": list(offering.supported_os),
    }
    image = resolve_verda_image(catalog_entry)
    return GpuProfile(
        name="interactive",
        instance_type=offering.instance_type,
        use_spot=use_spot,
        label=f"{offering.display_name} @ {offering.location}",
        location=offering.location,
        verda_image=image,
    )


def _load_dotenv_into_environ() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def terraform_base_args(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
) -> list[str]:
    args = [
        f"-var=run_id={run_id}",
        f"-var=max_session_hours={workload.max_session_hours}",
    ]
    client_id = os.environ.get("VERDA_CLIENT_ID", "")
    client_secret = os.environ.get("VERDA_CLIENT_SECRET", "")
    if client_id:
        args.append(f"-var=verda_client_id={client_id}")
    if client_secret:
        args.append(f"-var=verda_client_secret={client_secret}")
    for tfvar in workload.tfvars:
        args.append(f"-var-file={tfvar}")
    if profile:
        if not profile.verda_image:
            raise ValueError(f"profile {profile.name} missing verda_image — run prepare_deploy_chain first")
        args.append(f"-var=gpu_type={profile.instance_type}")
        args.append(f"-var=verda_image={profile.verda_image}")
        args.append(f"-var=use_spot={'true' if profile.use_spot else 'false'}")
        if profile.location:
            args.append(f"-var=location={profile.location}")
    return args


def terraform_apply_args(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
    *,
    replace_startup_script: bool = False,
) -> list[str]:
    args = ["apply", "-auto-approve"]
    if replace_startup_script:
        args.append("-replace=verda_startup_script.this")
    args.extend(terraform_base_args(workload, run_id, profile))
    return args


def terraform_destroy_args(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
) -> list[str]:
    return [
        "destroy",
        "-auto-approve",
        f"-target={_DESTROY_TARGET}",
        *terraform_base_args(workload, run_id, profile),
    ]


def session_uptime_hours(session: dict[str, Any], *, now: datetime | None = None) -> float:
    started = _parse_iso(session["started_at"])
    now = now or _utc_now()
    return max(0.0, (now - started).total_seconds() / 3600.0)


def idle_since_minutes(session: dict[str, Any], *, now: datetime | None = None) -> float:
    last = _parse_iso(session.get("last_activity_at") or session["started_at"])
    now = now or _utc_now()
    return max(0.0, (now - last).total_seconds() / 60.0)


def detect_activity(
    session: dict[str, Any],
    workload: WorkloadSpec,
    *,
    last_fingerprint: str | None = None,
) -> tuple[bool, str | None]:
    """Return (active, new_fingerprint)."""
    ip = session.get("ip")
    if not ip:
        return False, last_fingerprint

    if workload.health.type == "http" and workload.health.port:
        active, fingerprint = poll_comfyui_activity(ip, workload.health.port)
        if active:
            return True, fingerprint
        if last_fingerprint is not None and fingerprint != last_fingerprint:
            return True, fingerprint
        return False, fingerprint

    # SSH workloads: activity only via last_activity_at file-touch protocol.
    return False, last_fingerprint


def should_teardown(
    session: dict[str, Any],
    workload: WorkloadSpec,
    *,
    now: datetime | None = None,
    last_fingerprint: str | None = None,
) -> tuple[bool, str]:
    now = now or _utc_now()
    uptime_h = session_uptime_hours(session, now=now)
    if uptime_h >= workload.max_session_hours:
        return True, (
            f"HARD BUDGET CAP: session uptime {uptime_h:.2f}h >= "
            f"max_session_hours={workload.max_session_hours}"
        )

    active, _fp = detect_activity(session, workload, last_fingerprint=last_fingerprint)
    if active:
        return False, "activity detected"

    idle_min = idle_since_minutes(session, now=now)
    if idle_min >= workload.idle_minutes:
        return True, (
            f"IDLE: no activity for {idle_min:.1f}m >= idle_minutes={workload.idle_minutes}"
        )
    return False, f"ok (idle {idle_min:.1f}m)"


def watchdog_loop(
    workload_name: str,
    *,
    poll_sec: int = 60,
    state_path: Path = _STATE_PATH,
    once: bool = False,
) -> int:
    gpu_rates, gpu_profiles, workloads = load_registry()
    workload = workloads[workload_name]
    last_fingerprint: str | None = None

    while True:
        state = load_state(state_path)
        session = get_session(state, workload_name)
        if not session:
            log.error("no session for %s — watchdog exiting", workload_name)
            return 1

        active, last_fingerprint = detect_activity(
            session, workload, last_fingerprint=last_fingerprint
        )
        if active:
            record_activity(workload_name, path=state_path)

        teardown, reason = should_teardown(
            get_session(load_state(state_path), workload_name) or session,
            workload,
            last_fingerprint=last_fingerprint,
        )
        if teardown:
            log.warning("WATCHDOG TEARDOWN: %s", reason)
            ns = argparse.Namespace(workload=workload_name)
            return cmd_down(ns, gpu_rates, gpu_profiles, workloads)

        log.info(
            "watchdog ok workload=%s uptime=%.2fh idle=%.1fm cost=$%.4f",
            workload_name,
            session_uptime_hours(session),
            idle_since_minutes(session),
            estimate_cost_usd(session, gpu_rates),
        )
        if once:
            return 0
        time.sleep(poll_sec)


def _spawn_watchdog(workload: str, poll_sec: int = 60) -> None:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "watchdog",
        workload,
        "--poll-sec",
        str(poll_sec),
    ]
    log.info("spawning background watchdog: %s", " ".join(cmd))
    subprocess.Popen(
        cmd,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def cmd_watchdog(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    return watchdog_loop(
        args.workload,
        poll_sec=args.poll_sec,
        state_path=args.state_path,
        once=args.once,
    )


def cmd_run(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    state = load_state()
    session = get_session(state, args.workload)
    if not session or not is_session_live(session, workloads[args.workload], gpu_profiles):
        rc = cmd_up(args, gpu_rates, gpu_profiles, workloads)
        if rc != 0:
            return rc
        state = load_state()
        session = get_session(state, args.workload)
        if not session:
            return 1

    record_activity(args.workload)
    cmd = args.command
    if not cmd:
        log.error("run requires a command after --")
        return 1

    log.info("executing: %s", " ".join(shlex.quote(c) for c in cmd))
    _spawn_watchdog(args.workload, poll_sec=getattr(args, "poll_sec", 60))
    proc = subprocess.run(cmd, cwd=_REPO_ROOT)
    record_activity(args.workload)
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GeoPoAI GPU session manager")
    parser.add_argument("--state-path", type=Path, default=_STATE_PATH, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_workload(p: argparse.ArgumentParser) -> None:
        p.add_argument("workload", choices=["comfyui", "comfyui_setup", "blender_render", "lora_train"])

    p_up = sub.add_parser("up", help="terraform apply, wait for health, update .env")
    add_workload(p_up)
    p_up.add_argument("--run-id", default="auto")
    p_up.add_argument("--profile", help="force a gpu_profiles key (skip fallback chain)")
    p_up.add_argument("--verbose", action="store_true")
    p_up.set_defaults(func=cmd_up)

    p_gpus = sub.add_parser("gpus", help="Verda GET /instance-types [+ /instance-availability]")
    p_gpus.add_argument("--json", action="store_true", help="raw Verda API JSON")
    p_gpus.add_argument(
        "--location",
        default="FIN-01",
        help="location_code for availability column (default FIN-01)",
    )
    p_gpus.add_argument(
        "--all-locations",
        action="store_true",
        help="show free SKUs across all locations (same table as interactive wizard)",
    )
    p_gpus.add_argument("--include-cpu", action="store_true", help="include CPU SKUs in --all-locations")
    p_gpus.add_argument(
        "--sort-by",
        choices=["ondemand", "spot", "vram"],
        default="ondemand",
        help="sort for --all-locations",
    )
    p_gpus.set_defaults(func=cmd_gpus, workload=None)




    p_status = sub.add_parser("status", help="instance state, health, uptime, estimated cost")
    add_workload(p_status)
    p_status.set_defaults(func=cmd_status)

    p_down = sub.add_parser("down", help="destroy instance only (keeps models volume)")
    add_workload(p_down)
    p_down.set_defaults(func=cmd_down)

    p_run = sub.add_parser("run", help="up if needed, run command")
    add_workload(p_run)
    p_run.add_argument("--run-id", default="auto")
    p_run.add_argument("--verbose", action="store_true")
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="command after --")
    p_run.set_defaults(func=cmd_run)

    p_watch = sub.add_parser("watchdog", help="idle/budget watchdog loop (laptop side)")
    add_workload(p_watch)
    p_watch.add_argument("--poll-sec", type=int, default=60)
    p_watch.add_argument("--once", action="store_true", help="single poll iteration (testing)")
    p_watch.set_defaults(func=cmd_watchdog)

    return parser


def _normalize_run_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [gpu_session] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gpus":
        return int(cmd_gpus(args))

    gpu_rates, gpu_profiles, workloads = load_registry()



    if not getattr(args, "workload", None) or args.workload not in workloads:
        log.error("unknown workload: %s", getattr(args, "workload", None))
        return 1

    if args.command == "run":
        args.command = _normalize_run_command(args.command)

    return int(args.func(args, gpu_rates, gpu_profiles, workloads))


if __name__ == "__main__":
    raise SystemExit(main())

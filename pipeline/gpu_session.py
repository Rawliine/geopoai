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
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log.warning("Verda OAuth unreachable: %s", exc)
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
    # verda_client_id / verda_client_secret are NOT passed here — run_terraform injects
    # them as TF_VAR_* env so the secret never appears on the process command line.
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


def terraform_volume_apply_args(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile,
) -> list[str]:
    return [
        "apply",
        "-auto-approve",
        "-target=verda_volume.models",
        *terraform_base_args(workload, run_id, profile),
    ]


def apply_single_profile(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile,
) -> subprocess.CompletedProcess[str]:
    result = run_terraform(terraform_apply_args(workload, run_id, profile))
    if result.returncode != 0 and is_startup_script_immutable_error(result):
        log.warning("startup script immutable — retrying with -replace=verda_startup_script.this")
        result = run_terraform(
            terraform_apply_args(workload, run_id, profile, replace_startup_script=True),
        )
    return result


def ensure_volume_at_location(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile,
    volume: VolumeState,
    *,
    replace: bool = False,
) -> int:
    """Create or replace models volume in profile.location (terraform -target=verda_volume.models)."""
    if replace and volume.in_terraform_state:
        log.info("removing stale verda_volume.models from terraform state")
        rm = run_terraform(["state", "rm", "verda_volume.models"])
        if rm.returncode != 0:
            log.error("terraform state rm failed: %s", (rm.stderr or rm.stdout or "").strip())
            return rm.returncode
    result = run_terraform(terraform_volume_apply_args(workload, run_id, profile))
    if result.returncode != 0:
        log.error("volume apply failed: %s", (result.stderr or result.stdout or "").strip())
    return result.returncode


def resolve_ssh_private_key() -> Path | None:
    _load_dotenv_into_environ()
    env_key = os.environ.get("GEOPOAI_SSH_IDENTITY", "")
    if env_key and Path(env_key).expanduser().is_file():
        return Path(env_key).expanduser()
    for tfvar in ("workloads/comfyui.tfvars",):
        pub = _read_tfvar_string(tfvar, "ssh_public_key_path")
        if pub:
            pub_path = Path(pub.replace("~", str(Path.home())))
            priv = Path(str(pub_path)[:-4]) if str(pub_path).endswith(".pub") else pub_path
            if priv.is_file():
                return priv
    for candidate in (Path.home() / ".ssh" / "id_ed25519", Path.home() / ".ssh" / "id_rsa"):
        if candidate.is_file():
            return candidate
    return None


def run_ssh_on_instance(
    ip: str,
    remote_cmd: str,
    *,
    user: str = "root",
    identity: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    identity = identity or resolve_ssh_private_key()
    if not identity:
        raise RuntimeError("no SSH private key found")
    return subprocess.run(
        [
            "ssh",
            "-i",
            str(identity),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "IdentitiesOnly=yes",
            f"{user}@{ip}",
            remote_cmd,
        ],
        capture_output=True,
        text=True,
    )


def models_download_complete(ip: str, marker: str) -> bool:
    result = run_ssh_on_instance(ip, f"test -f {shlex.quote(marker)}")
    return result.returncode == 0


def run_download_on_vm(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None,
) -> int:
    """Sync repo + run download_models.sh on the live VM (wraps download_models_on_vm.sh)."""
    _load_dotenv_into_environ()
    hf = os.environ.get("TF_VAR_huggingface_token") or os.environ.get("HF_TOKEN", "")
    if not hf:
        log.error("set TF_VAR_huggingface_token or HF_TOKEN in .env")
        return 1
    os.environ["HF_TOKEN"] = hf
    os.environ["GEOPOAI_TF_REFRESH_ARGS"] = " ".join(terraform_base_args(workload, run_id, profile))
    script = _INFRA_DIR / "download_models_on_vm.sh"
    if not script.is_file():
        log.error("missing %s", script)
        return 1
    proc = subprocess.run([str(script), run_id], cwd=_INFRA_DIR)
    return proc.returncode


def finish_session_after_deploy(
    workload_name: str,
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile,
    gpu_profiles: dict[str, GpuProfile],
    *,
    wait_health: bool = True,
    verbose: bool = False,
    hourly_usd: float | None = None,
) -> tuple[int, dict[str, Any] | None]:
    ip = wait_for_instance_ip(workload, run_id, profile)
    instance_id = terraform_output("instance_id", workload, run_id, profile) or ""
    session: dict[str, Any] = {
        "workload": workload_name,
        "run_id": run_id,
        "started_at": _iso(_utc_now()),
        "last_activity_at": _iso(_utc_now()),
        "ip": ip,
        "instance_id": instance_id,
        "tfvars": workload.tfvars,
        "gpu_profile": profile.name,
        "gpu_type": profile.instance_type,
        "verda_image": profile.verda_image,
        "location": profile.location,
        "use_spot": profile.use_spot,
        "hourly_usd": hourly_usd,
    }
    state = load_state()
    state[workload_name] = session
    save_state(state)

    if workload.env_export:
        port = workload.health.port or 8188
        update_env_export(workload.env_export, f"http://{ip}:{port}")

    if wait_health:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            if check_health(session, workload):
                log.info("health check passed for %s at %s", workload_name, ip)
                break
            log.info("waiting for health (%s)...", workload.health.type)
            time.sleep(15)
        else:
            log.error("health check timed out for %s", workload_name)
            return 1, session

    if verbose:
        _tail_bootstrap_log(session, gpu_profiles)
    return 0, session


def prompt_download_if_needed(
    session: dict[str, Any],
    workload: WorkloadSpec,
    profile: GpuProfile | None,
    storage: StorageConfig,
    *,
    input_fn: Any = input,
    assume_yes: bool = False,
) -> int:
    ip = session.get("ip")
    if not ip:
        return 0
    marker = storage.models_marker
    if models_download_complete(ip, marker):
        print(f"Models marker present ({marker}) — skipping download.")
        return 0
    print(f"Models not found on volume (missing {marker}).")
    if not assume_yes:
        ans = input_fn("Run model download now? (1–3 hours) [Y/n]: ").strip().lower()
        if ans in ("n", "no"):
            print("Skipped download. Run: python pipeline/gpu_session.py setup <workload>")
            return 0
    return run_download_on_vm(workload, session["run_id"], profile)


def run_terraform(tf_args: list[str], *, cwd: Path = _INFRA_DIR) -> subprocess.CompletedProcess[str]:
    _load_dotenv_into_environ()
    cmd = ["terraform", *tf_args]
    env = os.environ.copy()
    # Hand Verda creds to terraform via TF_VAR_* env (read by var.verda_client_*),
    # not on argv — keeps the secret out of `ps` / shell history.
    for src, dst in (
        ("VERDA_CLIENT_ID", "TF_VAR_verda_client_id"),
        ("VERDA_CLIENT_SECRET", "TF_VAR_verda_client_secret"),
    ):
        val = os.environ.get(src, "")
        if val:
            env[dst] = val
    log.info("running: %s (cwd=%s)", " ".join(shlex.quote(a) for a in cmd), cwd)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def terraform_output(
    name: str,
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
) -> str | None:
    result = run_terraform(
        ["output", "-raw", name, *terraform_base_args(workload, run_id, profile)],
    )
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    if not value or value == "null":
        return None
    return value


def terraform_refresh(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
) -> None:
    run_terraform(["refresh", *terraform_base_args(workload, run_id, profile)])


def wait_for_instance_ip(
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile | None = None,
    *,
    max_wait_sec: int = 300,
    poll_sec: int = 10,
) -> str:
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        terraform_refresh(workload, run_id, profile)
        ip = terraform_output("instance_ip", workload, run_id, profile)
        if ip:
            log.info("instance_ip=%s", ip)
            return ip
        instance_id = terraform_output("instance_id", workload, run_id, profile)
        log.info("waiting for IP (instance_id=%s)...", instance_id or "?")
        time.sleep(poll_sec)
    raise RuntimeError(f"timed out waiting for instance_ip after {max_wait_sec}s")


def _http_probe(url: str, timeout: float = 10.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _ssh_probe(host: str, port: int = 22, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_health(session: dict[str, Any], workload: WorkloadSpec) -> bool:
    ip = session.get("ip")
    if not ip:
        return False
    if workload.health.type == "http":
        port = workload.health.port or 8188
        path = workload.health.path or "/"
        url = f"http://{ip}:{port}{path}"
        return _http_probe(url)
    if workload.health.type == "ssh":
        return _ssh_probe(ip)
    return False


def poll_comfyui_activity(ip: str, port: int = 8188) -> tuple[bool, str]:
    """Return (active, fingerprint) from ComfyUI /history and /queue."""
    fingerprints: list[str] = []
    active = False
    for path in ("/queue", "/history"):
        url = f"http://{ip}:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read()
            fingerprints.append(hashlib.sha256(body).hexdigest())
            payload = json.loads(body)
            if path == "/queue":
                if isinstance(payload, dict):
                    running = payload.get("queue_running") or []
                    pending = payload.get("queue_pending") or []
                    if running or pending:
                        active = True
            elif path == "/history" and isinstance(payload, dict) and payload:
                active = True
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
            continue
    fingerprint = "|".join(fingerprints)
    return active, fingerprint


def is_session_live(
    session: dict[str, Any],
    workload: WorkloadSpec,
    gpu_profiles: dict[str, GpuProfile] | None = None,
) -> bool:
    ip = session.get("ip")
    if not ip:
        return False
    if check_health(session, workload):
        return True
    profile = profile_for_session(session, gpu_profiles or {})
    run_id = session["run_id"]
    instance_id = terraform_output("instance_id", workload, run_id, profile)
    return bool(instance_id)


def generate_run_id(workload: str, state: dict[str, dict[str, Any]]) -> str:
    today = _utc_now().strftime("%Y-%m-%d")
    prefix = f"{workload}-{today}-"
    existing = [
        s["run_id"]
        for s in state.values()
        if isinstance(s.get("run_id"), str) and s["run_id"].startswith(prefix)
    ]
    n = 1
    while f"{prefix}{n}" in existing:
        n += 1
    return f"{prefix}{n}"


def update_env_export(key: str, value: str) -> None:
    # Back up the pre-session .env once; a later up must not clobber the original
    # (revert_env_export deletes the backup so the next session starts fresh).
    if _ENV_PATH.exists() and not _ENV_BAK_PATH.exists():
        _ENV_BAK_PATH.write_text(_ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    replaced = False
    out: list[str] = []
    for line in lines:
        if pattern.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    _ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    log.info("updated %s in .env (backup at .env.bak)", key)


def revert_env_export(key: str) -> None:
    if not _ENV_BAK_PATH.exists():
        return
    bak_lines = _ENV_BAK_PATH.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    original: str | None = None
    for line in bak_lines:
        if pattern.match(line):
            _, _, val = line.partition("=")
            original = val.strip()
            break
    if original is not None:
        update_env_export(key, original)
    # Backup served its purpose; drop it so the next session re-snapshots a clean .env.
    _ENV_BAK_PATH.unlink(missing_ok=True)


def hourly_rate_for_profile(
    profile: GpuProfile,
    catalog: dict[str, dict[str, Any]],
) -> float | None:
    """$/h for a profile from the Verda catalog — spot price if use_spot, else on-demand."""
    entry = catalog.get(profile.instance_type) or {}
    if profile.use_spot:
        spot = _float_or_none(entry.get("spot_price"))
        if spot is not None:
            return spot
    return _float_or_none(entry.get("price_per_hour"))


def estimate_cost_usd(
    session: dict[str, Any],
    gpu_rates: dict[str, float],
    *,
    now: datetime | None = None,
) -> float:
    started = _parse_iso(session["started_at"])
    now = now or _utc_now()
    hours = max(0.0, (now - started).total_seconds() / 3600.0)
    gpu_type = session.get("gpu_type") or ""
    # Prefer the live $/h captured at deploy time; fall back to the (usually empty)
    # registry table so cost is non-zero even when sessions.json carries no rates.
    rate = session.get("hourly_usd")
    if rate is None:
        rate = gpu_rates.get(gpu_type, 0.0)
    return round(hours * float(rate or 0.0), 4)


def apply_with_gpu_fallback(
    workload: WorkloadSpec,
    run_id: str,
    chain: list[GpuProfile],
) -> tuple[GpuProfile | None, subprocess.CompletedProcess[str]]:
    last_result: subprocess.CompletedProcess[str] | None = None
    for idx, profile in enumerate(chain):
        log.info(
            "trying gpu profile %s (%s) [%d/%d]",
            profile.name,
            profile.label,
            idx + 1,
            len(chain),
        )
        result = run_terraform(terraform_apply_args(workload, run_id, profile))
        if result.returncode != 0 and is_startup_script_immutable_error(result):
            log.warning(
                "profile %s: Verda startup script immutable — retrying with -replace=verda_startup_script.this",
                profile.name,
            )
            result = run_terraform(
                terraform_apply_args(workload, run_id, profile, replace_startup_script=True),
            )
        last_result = result
        if result.returncode == 0:
            return profile, result
        if is_service_unavailable(result):
            log.warning(
                "profile %s: Verda service_unavailable (503) — %s",
                profile.name,
                "trying next" if idx + 1 < len(chain) else "no profiles left",
            )
            continue
        log.warning("terraform apply exited %s for profile %s", result.returncode, profile.name)
        if result.stderr:
            log.warning("%s", result.stderr.strip())
        if is_definitive_apply_failure(result):
            return None, result
        # Ambiguous failure — instance may still be provisioning.
        return profile, result
    return None, last_result or subprocess.CompletedProcess([], 1, "", "")


def prepare_deploy_chain(
    workload: WorkloadSpec,
    gpu_profiles: dict[str, GpuProfile],
    *,
    force_profile: str | None = None,
) -> tuple[
    list[GpuProfile],
    dict[str, float],
    str,
    dict[str, set[str]] | None,
    dict[str, dict[str, Any]],
]:
    """Resolve best→worst chain using Verda GET /instance-types + /instance-availability."""
    raw_chain = profiles_to_try(workload, gpu_profiles, force_profile=force_profile)
    catalog_list = fetch_verda_instance_types()
    catalog = index_instance_types(catalog_list)
    rates = rates_from_catalog(catalog_list)
    location = resolve_workload_location(workload, raw_chain[0] if raw_chain else None)

    token = verda_oauth_token()
    availability: dict[str, set[str]] | None = None
    if token:
        availability = fetch_instance_availability_by_location(token)
        log.info("GET /instance-availability: %d locations", len(availability))
    else:
        log.warning(
            "GET /instance-availability skipped — set VERDA_CLIENT_ID/SECRET; "
            "will rely on service_unavailable at apply time"
        )

    chain = resolve_profiles_for_location(raw_chain, catalog, location, availability)
    if not chain:
        log.warning("no profiles pass availability filter — resolving images without pre-filter")
        chain = resolve_profiles_for_location(raw_chain, catalog, location, None)
    if not chain:
        raise ValueError(
            f"no deployable gpu profiles for {workload.name} at {location}; "
            "run: python pipeline/gpu_session.py gpus --location "
            f"{location}"
        )
    return chain, rates, location, availability, catalog


def cmd_gpus(args: argparse.Namespace) -> int:
    try:
        types = fetch_verda_instance_types()
    except (urllib.error.URLError, OSError, RuntimeError) as exc:
        print(f"# Verda API unreachable (GET /instance-types): {exc}", file=sys.stderr)
        return 1
    token = verda_oauth_token()
    availability = fetch_instance_availability_by_location(token) if token else None
    if args.json:
        payload: dict[str, Any] = {"instance_types": types}
        if availability is not None:
            payload["instance_availability"] = [
                {"location_code": k, "availabilities": sorted(v)}
                for k, v in sorted(availability.items())
            ]
        if token:
            payload["volumes"] = fetch_verda_volumes(token)
        print(json.dumps(payload, indent=2))
        return 0
    if getattr(args, "all_locations", False):
        if availability is None:
            print("# GET /v1/instance-availability requires VERDA_CLIENT_ID/SECRET in .env\n")
            return 1
        offerings = build_gpu_offerings(
            types,
            availability,
            include_cpu=getattr(args, "include_cpu", False),
            sort_by=getattr(args, "sort_by", "ondemand"),
        )
        print(format_gpu_offerings_table(offerings))
        return 0
    location = args.location or "FIN-01"
    if availability is None:
        print("# GET /v1/instance-availability requires VERDA_CLIENT_ID/SECRET in .env\n")
    print(format_gpu_catalog(types, spot=False, availability=availability, location=location))
    print()
    print(format_gpu_catalog(types, spot=True, availability=availability, location=location))
    return 0


def cmd_up(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    workload = workloads[args.workload]
    state = load_state()

    existing = get_session(state, args.workload)
    if existing and is_session_live(existing, workload, gpu_profiles):
        log.error(
            "refusing up: live session for %s (run_id=%s ip=%s)",
            args.workload,
            existing.get("run_id"),
            existing.get("ip"),
        )
        return 1

    run_id = args.run_id
    if run_id == "auto":
        run_id = generate_run_id(args.workload, state)

    try:
        chain, _catalog_rates, location, _avail, catalog = prepare_deploy_chain(
            workload,
            gpu_profiles,
            force_profile=getattr(args, "profile", None),
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    log.info(
        "bringing up %s run_id=%s @ %s (gpu chain: %s)",
        args.workload,
        run_id,
        location,
        " → ".join(f"{p.name}[{p.instance_type}]" for p in chain),
    )
    chosen_profile, result = apply_with_gpu_fallback(workload, run_id, chain)
    if chosen_profile is None:
        log.error(
            "terraform apply failed for all profiles — %s",
            "Verda service_unavailable for every SKU"
            if result and is_service_unavailable(result)
            else "see terraform output above",
        )
        if result and result.stderr:
            log.error("%s", result.stderr.strip())
        return 1
    if result.returncode != 0:
        log.error("terraform apply failed for profile %s", chosen_profile.name)
        if result.stderr:
            log.error("%s", result.stderr.strip())
        return 1

    ip = wait_for_instance_ip(workload, run_id, chosen_profile)
    instance_id = terraform_output("instance_id", workload, run_id, chosen_profile) or ""

    session: dict[str, Any] = {
        "workload": args.workload,
        "run_id": run_id,
        "started_at": _iso(_utc_now()),
        "last_activity_at": _iso(_utc_now()),
        "ip": ip,
        "instance_id": instance_id,
        "tfvars": workload.tfvars,
        "gpu_profile": chosen_profile.name,
        "gpu_type": chosen_profile.instance_type,
        "verda_image": chosen_profile.verda_image,
        "location": location,
        "use_spot": chosen_profile.use_spot,
        "hourly_usd": hourly_rate_for_profile(chosen_profile, catalog),
    }
    state[args.workload] = session
    save_state(state)

    if workload.env_export:
        port = workload.health.port or 8188
        update_env_export(workload.env_export, f"http://{ip}:{port}")

    # Health poll
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if check_health(session, workload):
            log.info("health check passed for %s at %s", args.workload, ip)
            break
        log.info("waiting for health (%s)...", workload.health.type)
        time.sleep(15)
    else:
        log.error("health check timed out for %s", args.workload)
        return 1

    if args.verbose:
        _tail_bootstrap_log(session, gpu_profiles)

    print(json.dumps(session, indent=2))
    return 0


def _tail_bootstrap_log(
    session: dict[str, Any],
    gpu_profiles: dict[str, GpuProfile],
) -> None:
    ssh_script = _INFRA_DIR / "verda_ssh.sh"
    if not ssh_script.exists():
        return
    workload = WorkloadSpec(
        name=session["workload"],
        tfvars=session["tfvars"],
        health=HealthSpec(type="ssh"),
        env_export=None,
        default_gpu_profile="",
        gpu_preference=[],
        idle_minutes=0,
        max_session_hours=0,
    )
    profile = profile_for_session(session, gpu_profiles)
    os.environ["GEOPOAI_TF_REFRESH_ARGS"] = " ".join(
        terraform_base_args(workload, session["run_id"], profile)
    )
    log.info("streaming bootstrap log (Ctrl-C to stop tail; VM keeps running)")
    try:
        subprocess.run(
            [str(ssh_script), "--", "tail", "-n", "50", "/var/log/geopoai-bootstrap.log"],
            cwd=_INFRA_DIR,
            check=False,
        )
    except KeyboardInterrupt:
        log.info("stopped tailing bootstrap log")


def cmd_status(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    workload = workloads[args.workload]
    state = load_state()
    session = get_session(state, args.workload)
    if not session:
        print(json.dumps({"workload": args.workload, "status": "down"}))
        return 0

    healthy = check_health(session, workload)
    live = is_session_live(session, workload, gpu_profiles)
    status = "up" if live else "stale"
    started = _parse_iso(session["started_at"])
    uptime_hours = (_utc_now() - started).total_seconds() / 3600.0
    report = {
        "workload": args.workload,
        "status": status,
        "run_id": session["run_id"],
        "ip": session.get("ip"),
        "instance_id": session.get("instance_id"),
        "healthy": healthy,
        "uptime_hours": round(uptime_hours, 3),
        "estimated_cost_usd": estimate_cost_usd(session, gpu_rates),
        "gpu_profile": session.get("gpu_profile"),
        "gpu_type": session.get("gpu_type"),
        "started_at": session.get("started_at"),
        "last_activity_at": session.get("last_activity_at"),
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_down(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    workload = workloads[args.workload]
    state = load_state()
    session = get_session(state, args.workload)
    if not session:
        log.info("no session state for %s — nothing to tear down", args.workload)
        return 0

    run_id = session["run_id"]
    profile = profile_for_session(session, gpu_profiles)
    log.info(
        "destroying instance only for %s run_id=%s profile=%s",
        args.workload,
        run_id,
        profile.name if profile else "?",
    )
    result = run_terraform(terraform_destroy_args(workload, run_id, profile))
    if result.returncode != 0:
        log.error("terraform destroy failed: %s", (result.stderr or result.stdout or "").strip())
        return result.returncode

    if workload.env_export:
        revert_env_export(workload.env_export)

    state.pop(args.workload, None)
    save_state(state)
    log.info("session down; models volume untouched")
    return 0


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _prompt_workload(input_fn: Any = input) -> str:
    choices = ["comfyui_setup", "comfyui", "blender_render", "lora_train"]
    print("Select workload:")
    for i, name in enumerate(choices, start=1):
        print(f"  {i}) {name}")
    while True:
        raw = input_fn("Workload [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        if raw in choices:
            return raw
        print("Invalid choice.")


def _browse_offerings_interactive(
    catalog: list[dict[str, Any]],
    availability: dict[str, set[str]],
    *,
    location_filter: str | None = None,
    input_fn: Any = input,
) -> GpuOffering | None:
    sort_by = "ondemand"
    while True:
        offerings = build_gpu_offerings(
            catalog,
            availability,
            location_filter=location_filter,
            sort_by=sort_by,
        )
        if not offerings:
            print("No free GPU SKUs" + (f" in {location_filter}" if location_filter else "") + ".")
            return None
        print(format_gpu_offerings_table(offerings, title=f"Sort: {sort_by}"))
        raw = input_fn("Pick: ").strip().lower()
        if raw in ("q", "quit"):
            return None
        if raw in ("r", "refresh"):
            catalog = fetch_verda_instance_types()
            token = verda_oauth_token()
            if token:
                availability = fetch_instance_availability_by_location(token)
            continue
        if raw in ("s", "sort"):
            sort_by = input_fn("Sort by ondemand/spot/vram [ondemand]: ").strip().lower() or "ondemand"
            if sort_by not in ("ondemand", "spot", "vram"):
                sort_by = "ondemand"
            continue
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(offerings):
                return offerings[idx - 1]
        print("Invalid pick.")


def _interactive_resolve_volume(
    offering: GpuOffering,
    workload: WorkloadSpec,
    run_id: str,
    profile: GpuProfile,
    storage: StorageConfig,
    token: str | None,
    *,
    input_fn: Any = input,
) -> int:
    volume = read_volume_state(token, storage)
    print("\n--- Models volume ---")
    if volume.id:
        print(
            f"  id={volume.id} name={volume.name} location={volume.location} "
            f"size={volume.size_gb}GB status={volume.status} "
            f"~${volume.monthly_cost_estimate}/mo"
        )
    else:
        print("  No volume in Terraform state / Verda.")

    vol_loc = volume.location
    gpu_loc = offering.location

    if not volume.id or volume.status == "deleted":
        ans = input_fn(f"Create {storage.default_volume_size_gb}GB volume in {gpu_loc}? [Y/n]: ").strip().lower()
        if ans in ("n", "no"):
            return 1
        return ensure_volume_at_location(workload, run_id, profile, volume, replace=bool(volume.in_terraform_state))

    if vol_loc and vol_loc != gpu_loc:
        print(f"Region mismatch: volume={vol_loc} GPU={gpu_loc}")
        print("  A) Re-browse GPUs in volume region")
        print("  B) Replace volume in GPU region (DESTROY-VOLUME confirm; weights lost)")
        print("  C) Cancel")
        choice = input_fn("Choice [A]: ").strip().upper() or "A"
        if choice == "C":
            return 1
        if choice == "B":
            confirm = input_fn("Type DESTROY-VOLUME to confirm replacing volume: ").strip()
            if confirm != "DESTROY-VOLUME":
                print("Aborted.")
                return 1
            if instance_in_terraform_state():
                print("Destroy the instance first: gpu_session destroy instance <workload>")
                return 1
            return ensure_volume_at_location(workload, run_id, profile, volume, replace=True)
        return 2  # signal re-browse in volume region

    return 0


def cmd_interactive(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    if not _is_tty() and not getattr(args, "force", False):
        print(
            "interactive requires a TTY.\n"
            "Try: python pipeline/gpu_session.py gpus --all-locations\n"
            "     python pipeline/gpu_session.py up <workload> --profile <name>",
            file=sys.stderr,
        )
        return 1

    input_fn = getattr(args, "input_fn", input)
    storage = load_storage_config()

    if getattr(args, "teardown", False):
        return _interactive_teardown(input_fn=input_fn, gpu_rates=gpu_rates, gpu_profiles=gpu_profiles, workloads=workloads)

    workload_name = getattr(args, "workload", None) or _prompt_workload(input_fn)
    workload = workloads[workload_name]
    state = load_state()
    if get_session(state, workload_name) and is_session_live(
        get_session(state, workload_name) or {}, workload, gpu_profiles
    ):
        log.error("live session exists for %s — run destroy instance first", workload_name)
        return 1

    token = verda_oauth_token()
    if not token:
        log.error("set VERDA_CLIENT_ID and VERDA_CLIENT_SECRET in .env")
        return 1

    catalog = fetch_verda_instance_types()
    availability = fetch_instance_availability_by_location(token)
    location_filter: str | None = None

    while True:
        offering = _browse_offerings_interactive(
            catalog, availability, location_filter=location_filter, input_fn=input_fn
        )
        if offering is None:
            return 1

        print(f"\nSelected: {offering.instance_type} @ {offering.location}")
        print(f"  On-demand: ${offering.price_ondemand or '?'}/h  Spot: ${offering.price_spot or '?'}/h")
        billing = input_fn("Billing on-demand or spot? [on-demand/spot]: ").strip().lower()
        use_spot = billing.startswith("s")
        if use_spot and offering.price_spot is None:
            print("No spot price in catalog — using on-demand.")
            use_spot = False

        profile = offering_to_profile(offering, use_spot=use_spot)
        run_id = input_fn("run_id [auto]: ").strip() or "auto"
        if run_id == "auto":
            run_id = generate_run_id(workload_name, load_state())

        vol_rc = _interactive_resolve_volume(
            offering, workload, run_id, profile, storage, token, input_fn=input_fn
        )
        if vol_rc == 2:
            location_filter = read_volume_state(token, storage).location
            continue
        if vol_rc != 0:
            return 1

        price = offering.price_spot if use_spot else offering.price_ondemand
        vol = read_volume_state(token, storage)
        print("\n--- Confirm deploy ---")
        print(f"  workload={workload_name} run_id={run_id}")
        print(f"  {offering.instance_type} @ {offering.location} spot={use_spot} ~${price or '?'}/h")
        print(f"  volume={vol.id or 'new'} ({vol.location})")
        if input_fn("Proceed? [yes/NO]: ").strip().lower() != "yes":
            print("Aborted.")
            return 1

        result = apply_single_profile(workload, run_id, profile)
        if result.returncode != 0:
            if is_service_unavailable(result):
                print("Verda service_unavailable — pick another GPU (refreshing).")
                catalog = fetch_verda_instance_types()
                availability = fetch_instance_availability_by_location(token)
                continue
            log.error("apply failed: %s", (result.stderr or result.stdout or "").strip())
            return 1

        rc, session = finish_session_after_deploy(
            workload_name,
            workload,
            run_id,
            profile,
            gpu_profiles,
            wait_health=True,
            verbose=getattr(args, "verbose", False),
            hourly_usd=(offering.price_spot if use_spot else offering.price_ondemand),
        )
        if rc != 0 or not session:
            return rc

        dl_rc = prompt_download_if_needed(session, workload, profile, storage, input_fn=input_fn)
        if dl_rc != 0:
            return dl_rc

        ssh = terraform_output("ssh_command", workload, run_id, profile) or f"ssh ubuntu@{session['ip']}"
        print("\n--- Session ready ---")
        print(json.dumps(session, indent=2))
        print(f"\nSSH: {ssh}")
        print(f"Status: python pipeline/gpu_session.py status {workload_name}")
        print(f"Teardown: python pipeline/gpu_session.py destroy instance {workload_name}")
        return 0


def _interactive_teardown(
    *,
    input_fn: Any,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    print("Teardown menu:")
    print("  1) Destroy instance only (keep volume)")
    print("  2) Destroy volume only (instance must be down)")
    print("  3) Destroy instance then volume")
    print("  q) Quit")
    raw = input_fn("Choice: ").strip()
    if raw == "1":
        wl = _prompt_workload(input_fn)
        ns = argparse.Namespace(workload=wl)
        return cmd_destroy_instance(ns, gpu_rates, gpu_profiles, workloads)
    if raw == "2":
        return cmd_destroy_volume(argparse.Namespace(), gpu_rates, gpu_profiles, workloads, input_fn=input_fn)
    if raw == "3":
        wl = _prompt_workload(input_fn)
        ns = argparse.Namespace(workload=wl)
        rc = cmd_destroy_instance(ns, gpu_rates, gpu_profiles, workloads)
        if rc != 0:
            return rc
        return cmd_destroy_volume(argparse.Namespace(), gpu_rates, gpu_profiles, workloads, input_fn=input_fn)
    return 0


def cmd_destroy_instance(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    return cmd_down(args, gpu_rates, gpu_profiles, workloads)


def cmd_destroy_volume(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
    *,
    input_fn: Any = input,
) -> int:
    if instance_in_terraform_state():
        log.error("instance still in terraform state — run: gpu_session destroy instance <workload>")
        return 1
    state = load_state()
    for wl, sess in state.items():
        if sess.get("ip") and is_session_live(sess, workloads.get(wl, workloads["comfyui_setup"]), gpu_profiles):
            log.error("live session for %s — destroy instance first", wl)
            return 1

    token = verda_oauth_token()
    if not token:
        log.error("VERDA_CLIENT_ID/SECRET required")
        return 1
    storage = load_storage_config()
    volume = read_volume_state(token, storage)
    if not volume.id:
        log.info("no models volume to destroy")
        return 0

    print(f"Volume: {volume.name} id={volume.id} location={volume.location} "
          f"size={volume.size_gb}GB ~${volume.monthly_cost_estimate}/mo status={volume.status}")
    if input_fn("Destroy this volume? Type 'yes': ").strip().lower() != "yes":
        print("Aborted.")
        return 1
    name_confirm = volume.name or ""
    if input_fn(f"Type exact volume name to confirm [{name_confirm}]: ").strip() != name_confirm:
        print("Aborted.")
        return 1

    try:
        verda_api_delete(f"volumes/{volume.id}", token=token)
    except (urllib.error.HTTPError, OSError) as exc:
        log.error("Verda DELETE volume failed: %s", exc)
        return 1

    if volume.in_terraform_state:
        rm = run_terraform(["state", "rm", "verda_volume.models"])
        if rm.returncode != 0:
            log.warning("terraform state rm failed (volume deleted in Verda): %s", rm.stderr)

    log.info("volume destroyed in Verda; terraform state cleared")
    return 0


def cmd_setup(
    args: argparse.Namespace,
    gpu_rates: dict[str, float],
    gpu_profiles: dict[str, GpuProfile],
    workloads: dict[str, WorkloadSpec],
) -> int:
    workload = workloads[args.workload]
    storage = load_storage_config()
    state = load_state()
    session = get_session(state, args.workload)
    if not session:
        log.error("no session state for %s — run interactive or up first", args.workload)
        return 1
    if not is_session_live(session, workload, gpu_profiles):
        log.error("session not live for %s", args.workload)
        return 1
    profile = profile_for_session(session, gpu_profiles)
    ip = session.get("ip")
    if not ip:
        ip = wait_for_instance_ip(workload, session["run_id"], profile)
        session["ip"] = ip
        state[args.workload] = session
        save_state(state)

    if models_download_complete(ip, storage.models_marker):
        print(f"Models already complete ({storage.models_marker})")
        return 0
    if getattr(args, "yes", False):
        return run_download_on_vm(workload, session["run_id"], profile)
    return prompt_download_if_needed(
        session, workload, profile, storage, assume_yes=False,
        input_fn=getattr(args, "input_fn", input),
    )


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


def _watchdog_pidfile(workload: str) -> Path:
    return _INFRA_DIR / f".watchdog_{workload}.pid"


def _watchdog_running(workload: str) -> bool:
    pf = _watchdog_pidfile(workload)
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _spawn_watchdog(workload: str, poll_sec: int = 60) -> None:
    if _watchdog_running(workload):
        log.info("watchdog already running for %s — not spawning another", workload)
        return
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "watchdog",
        workload,
        "--poll-sec",
        str(poll_sec),
    ]
    log.info("spawning background watchdog: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _watchdog_pidfile(workload).write_text(f"{proc.pid}\n", encoding="utf-8")
    except OSError:
        pass


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
    cmd = _normalize_run_command(args.cmd)
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

    p_inter = sub.add_parser("interactive", help="browse GPUs, pick region/SKU, deploy, optional download")
    p_inter.add_argument("workload", nargs="?", help="skip workload prompt if given")
    p_inter.add_argument("--teardown", action="store_true", help="teardown submenu (instance/volume)")
    p_inter.add_argument("--verbose", action="store_true")
    p_inter.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    p_inter.set_defaults(func=cmd_interactive, workload=None)

    p_setup = sub.add_parser("setup", help="conditional model download on live instance")
    add_workload(p_setup)
    p_setup.add_argument("-y", "--yes", action="store_true", help="run download without prompting")
    p_setup.set_defaults(func=cmd_setup)

    p_destroy = sub.add_parser("destroy", help="tear down instance or volume")
    destroy_sub = p_destroy.add_subparsers(dest="destroy_target", required=True)
    p_destroy_inst = destroy_sub.add_parser("instance", help="destroy VM only (keeps models volume)")
    add_workload(p_destroy_inst)
    p_destroy_inst.set_defaults(func=cmd_destroy_instance)
    p_destroy_vol = destroy_sub.add_parser("volume", help="destroy models block volume (confirmed)")
    p_destroy_vol.set_defaults(func=cmd_destroy_volume, workload=None)

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
    # Named `cmd` (not `command`) to avoid clobbering the subparser dest="command".
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, help="command after --")
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

    if args.command == "interactive":
        if getattr(args, "workload", None):
            args.workload = args.workload  # positional optional
        return int(cmd_interactive(args, gpu_rates, gpu_profiles, workloads))

    if args.command == "destroy" and getattr(args, "destroy_target", None) == "volume":
        return int(cmd_destroy_volume(args, gpu_rates, gpu_profiles, workloads))

    if not getattr(args, "workload", None) or args.workload not in workloads:
        log.error("unknown workload: %s", getattr(args, "workload", None))
        return 1

    return int(args.func(args, gpu_rates, gpu_profiles, workloads))


if __name__ == "__main__":
    raise SystemExit(main())

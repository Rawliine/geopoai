#!/usr/bin/env python3
"""pipeline/gpu_session.py — Generic GPU session manager for Verda workloads.

Lifecycle: up → health → use → auto-down (via watchdog / budget caps).

NEVER destroys verda_volume.models — only verda_instance.this is targeted.
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
class WorkloadSpec:
    name: str
    tfvars: list[str]
    health: HealthSpec
    env_export: str | None
    default_gpu_profile: str
    idle_minutes: int
    max_session_hours: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_registry(path: Path = _SESSIONS_PATH) -> tuple[dict[str, float], dict[str, WorkloadSpec]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    gpu_rates = {str(k): float(v) for k, v in raw["gpu_hourly_usd"].items()}
    workloads: dict[str, WorkloadSpec] = {}
    for name, entry in raw["workloads"].items():
        health_raw = entry["health"]
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
            idle_minutes=int(entry["idle_minutes"]),
            max_session_hours=int(entry["max_session_hours"]),
        )
    return gpu_rates, workloads


def load_state(path: Path = _STATE_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, dict[str, Any]], path: Path = _STATE_PATH) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_session(state: dict[str, dict[str, Any]], workload: str) -> dict[str, Any] | None:
    return state.get(workload)


def record_activity(workload: str, *, path: Path = _STATE_PATH) -> None:
    """Update last_activity_at for a workload (file-touch fallback for idle watchdog)."""
    state = load_state(path)
    session = state.get(workload)
    if not session:
        return
    session["last_activity_at"] = _iso(_utc_now())
    save_state(state, path)


def _read_gpu_type_from_tfvars(tfvars_rel: str) -> str | None:
    path = _INFRA_DIR / tfvars_rel
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*gpu_type\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    return None


def resolve_gpu_type(workload: WorkloadSpec) -> str:
    for tfvar in workload.tfvars:
        gpu = _read_gpu_type_from_tfvars(tfvar)
        if gpu:
            return gpu
    return workload.default_gpu_profile


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


def terraform_base_args(workload: WorkloadSpec, run_id: str) -> list[str]:
    args = [f"-var=run_id={run_id}"]
    if os.environ.get("GEOPOAI_PASS_MAX_SESSION_HOURS") == "1":
        args.append(f"-var=max_session_hours={workload.max_session_hours}")
    for tfvar in workload.tfvars:
        args.append(f"-var-file={tfvar}")
    return args


def terraform_apply_args(workload: WorkloadSpec, run_id: str) -> list[str]:
    return ["apply", "-auto-approve", *terraform_base_args(workload, run_id)]


def terraform_destroy_args(workload: WorkloadSpec, run_id: str) -> list[str]:
    return [
        "destroy",
        "-auto-approve",
        f"-target={_DESTROY_TARGET}",
        *terraform_base_args(workload, run_id),
    ]


def run_terraform(tf_args: list[str], *, cwd: Path = _INFRA_DIR) -> subprocess.CompletedProcess[str]:
    _load_dotenv_into_environ()
    cmd = ["terraform", *tf_args]
    log.info("running: %s (cwd=%s)", " ".join(shlex.quote(a) for a in cmd), cwd)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def terraform_output(name: str, workload: WorkloadSpec, run_id: str) -> str | None:
    result = run_terraform(
        ["output", "-raw", name, *terraform_base_args(workload, run_id)],
    )
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    if not value or value == "null":
        return None
    return value


def terraform_refresh(workload: WorkloadSpec, run_id: str) -> None:
    run_terraform(["refresh", *terraform_base_args(workload, run_id)])


def wait_for_instance_ip(
    workload: WorkloadSpec,
    run_id: str,
    *,
    max_wait_sec: int = 300,
    poll_sec: int = 10,
) -> str:
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        terraform_refresh(workload, run_id)
        ip = terraform_output("instance_ip", workload, run_id)
        if ip:
            log.info("instance_ip=%s", ip)
            return ip
        instance_id = terraform_output("instance_id", workload, run_id)
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


def is_session_live(session: dict[str, Any], workload: WorkloadSpec) -> bool:
    ip = session.get("ip")
    if not ip:
        return False
    if check_health(session, workload):
        return True
    # Terraform may still report instance id while booting.
    run_id = session["run_id"]
    instance_id = terraform_output("instance_id", workload, run_id)
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
    if _ENV_PATH.exists():
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
    for line in bak_lines:
        if pattern.match(line):
            _, _, val = line.partition("=")
            update_env_export(key, val.strip())
            return


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
    rate = gpu_rates.get(gpu_type, 0.0)
    return round(hours * rate, 4)


def cmd_up(args: argparse.Namespace, gpu_rates: dict[str, float], workloads: dict[str, WorkloadSpec]) -> int:
    workload = workloads[args.workload]
    state = load_state()

    existing = get_session(state, args.workload)
    if existing and is_session_live(existing, workload):
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

    log.info("bringing up %s run_id=%s", args.workload, run_id)
    result = run_terraform(terraform_apply_args(workload, run_id))
    if result.returncode != 0:
        log.warning("terraform apply exited %s", result.returncode)
        if result.stderr:
            log.warning("%s", result.stderr.strip())
        # Verda often assigns IP after apply returns — continue if instance exists.

    ip = wait_for_instance_ip(workload, run_id)
    instance_id = terraform_output("instance_id", workload, run_id) or ""

    session: dict[str, Any] = {
        "workload": args.workload,
        "run_id": run_id,
        "started_at": _iso(_utc_now()),
        "last_activity_at": _iso(_utc_now()),
        "ip": ip,
        "instance_id": instance_id,
        "tfvars": workload.tfvars,
        "gpu_type": resolve_gpu_type(workload),
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
        _tail_bootstrap_log(session)

    print(json.dumps(session, indent=2))
    return 0


def _tail_bootstrap_log(session: dict[str, Any]) -> None:
    ssh_script = _INFRA_DIR / "verda_ssh.sh"
    if not ssh_script.exists():
        return
    os.environ["GEOPOAI_TF_REFRESH_ARGS"] = " ".join(
        terraform_base_args(
            WorkloadSpec(
                name=session["workload"],
                tfvars=session["tfvars"],
                health=HealthSpec(type="ssh"),
                env_export=None,
                default_gpu_profile="",
                idle_minutes=0,
                max_session_hours=0,
            ),
            session["run_id"],
        )
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


def cmd_status(args: argparse.Namespace, gpu_rates: dict[str, float], workloads: dict[str, WorkloadSpec]) -> int:
    workload = workloads[args.workload]
    state = load_state()
    session = get_session(state, args.workload)
    if not session:
        print(json.dumps({"workload": args.workload, "status": "down"}))
        return 0

    healthy = check_health(session, workload)
    live = is_session_live(session, workload)
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
        "gpu_type": session.get("gpu_type"),
        "started_at": session.get("started_at"),
        "last_activity_at": session.get("last_activity_at"),
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_down(args: argparse.Namespace, gpu_rates: dict[str, float], workloads: dict[str, WorkloadSpec]) -> int:
    workload = workloads[args.workload]
    state = load_state()
    session = get_session(state, args.workload)
    if not session:
        log.info("no session state for %s — nothing to tear down", args.workload)
        return 0

    run_id = session["run_id"]
    log.info("destroying instance only for %s run_id=%s", args.workload, run_id)
    result = run_terraform(terraform_destroy_args(workload, run_id))
    if result.returncode != 0:
        log.error("terraform destroy failed: %s", (result.stderr or result.stdout or "").strip())
        return result.returncode

    if workload.env_export:
        revert_env_export(workload.env_export)

    state.pop(args.workload, None)
    save_state(state)
    log.info("session down; models volume untouched")
    return 0


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
    gpu_rates, workloads = load_registry()
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
            return cmd_down(ns, gpu_rates, workloads)

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


def cmd_watchdog(args: argparse.Namespace, gpu_rates: dict[str, float], workloads: dict[str, WorkloadSpec]) -> int:
    return watchdog_loop(
        args.workload,
        poll_sec=args.poll_sec,
        state_path=args.state_path,
        once=args.once,
    )


def cmd_run(args: argparse.Namespace, gpu_rates: dict[str, float], workloads: dict[str, WorkloadSpec]) -> int:
    state = load_state()
    session = get_session(state, args.workload)
    if not session or not is_session_live(session, workloads[args.workload]):
        rc = cmd_up(args, gpu_rates, workloads)
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
    p_up.add_argument("--verbose", action="store_true")
    p_up.set_defaults(func=cmd_up)

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

    gpu_rates, workloads = load_registry()
    if args.workload not in workloads:
        log.error("unknown workload: %s", args.workload)
        return 1

    if args.command == "run":
        args.command = _normalize_run_command(args.command)

    return int(args.func(args, gpu_rates, workloads))


if __name__ == "__main__":
    raise SystemExit(main())

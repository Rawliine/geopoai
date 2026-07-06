"""broll.lib.comfyui_lifecycle — keep the ComfyUI server alive for AI b-roll.

The AI b-roll path (``broll.sources.ltx_video`` / ``flux_ltx_video``) needs a
running ComfyUI at ``BROLL_COMFYUI_URL``. A whole episode has failed before
because ComfyUI simply wasn't up and nothing tried to bring it back. This module
adds a preflight: check liveness, and if the server is down, attempt a restart
and wait for it to come back before generation proceeds.

Restart model (Verda-first): everything runs on the GPU box, where ComfyUI is
served in a tmux session named ``comfyui`` (see
``infra/startup_scripts/comfyui_bootstrap.sh``). The default restart relaunches
that tmux session locally. Override the whole command with
``BROLL_COMFYUI_RESTART_CMD`` when ComfyUI lives on a different host (e.g. an
``ssh <box> '<serve>'``). ``COMFYUI_HOME`` (default ``/home/ubuntu/ComfyUI``)
locates the checkout for the default command.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from broll.lib.errors import BrollError

log = logging.getLogger("broll.comfyui_lifecycle")

_DEFAULT_HOME = "/home/ubuntu/ComfyUI"
_HEALTH_PATH = "/system_stats"


class ComfyUnavailableError(BrollError):
    """ComfyUI is down and could not be restarted."""


def is_alive(url: str, *, timeout: float = 3.0) -> bool:
    """True if ComfyUI answers its ``/system_stats`` endpoint."""
    probe = f"{url.rstrip('/')}{_HEALTH_PATH}"
    try:
        with urllib.request.urlopen(probe, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _port_of(url: str) -> int:
    return urlsplit(url).port or 8188


def _default_restart_cmd(url: str) -> str | None:
    """Relaunch the local ``comfyui`` tmux session, or None if tmux is absent."""
    if shutil.which("tmux") is None:
        return None
    home = os.environ.get("COMFYUI_HOME", _DEFAULT_HOME)
    port = _port_of(url)
    serve = (
        f"cd {home} && . .venv/bin/activate && "
        f"exec python main.py --listen 0.0.0.0 --port {port}"
    )
    return (
        "tmux kill-session -t comfyui 2>/dev/null; "
        f'tmux new-session -d -s comfyui "{serve}"'
    )


def _restart(url: str) -> bool:
    """Attempt to (re)start ComfyUI. Returns True if a restart command ran."""
    cmd = os.environ.get("BROLL_COMFYUI_RESTART_CMD") or _default_restart_cmd(url)
    if not cmd:
        log.warning(
            "ComfyUI down and no restart available (no tmux, no "
            "BROLL_COMFYUI_RESTART_CMD); leave it to the operator"
        )
        return False
    log.info("restarting ComfyUI: %s", cmd)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        log.warning("ComfyUI restart command exited %d: %s",
                    res.returncode, (res.stderr or "")[-500:])
    return True


def ensure_up(
    url: str,
    *,
    attempts: int = 3,
    wait_s: float = 8.0,
    poll_timeout_s: float = 90.0,
) -> None:
    """Ensure ComfyUI at *url* is answering; restart and wait if not.

    Fast path: already alive → return immediately. Otherwise restart, then poll
    up to *poll_timeout_s* for liveness, retrying the restart up to *attempts*
    times. Raises :class:`ComfyUnavailableError` if still down.
    """
    if is_alive(url):
        return
    log.info("ComfyUI not responding at %s — attempting restart", url)
    for attempt in range(1, attempts + 1):
        restarted = _restart(url)
        deadline = time.monotonic() + poll_timeout_s
        while time.monotonic() < deadline:
            if is_alive(url):
                log.info("ComfyUI back up at %s (attempt %d)", url, attempt)
                return
            time.sleep(wait_s)
        if not restarted:
            break  # nothing we can do; don't spin the full attempt budget
        log.warning("ComfyUI still down after attempt %d/%d", attempt, attempts)
    raise ComfyUnavailableError(
        f"ComfyUI at {url} is unavailable and could not be restarted. "
        f"Bring it up (tmux session 'comfyui' on the GPU box) or set "
        f"BROLL_COMFYUI_RESTART_CMD."
    )

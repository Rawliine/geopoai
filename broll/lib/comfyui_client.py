"""broll.lib.comfyui_client — HTTP client for a ComfyUI instance.

The Verda ComfyUI box (see ``infra/verda_workflow(2).md``) exposes the
standard ComfyUI API on port 8188:

* ``POST /prompt``        — submit a workflow graph, get a ``prompt_id``
* ``GET  /history/<id>``  — completion poll; result references live here
* ``GET  /view``          — download a saved output file

This module wraps those three endpoints, handles the realities of running
against a spot-priced GPU (mid-job connection drops, slow first-token
latency, occasional 5xx during model warm-up), and produces a single
:class:`ComfyJobResult` per submission.

Configuration
-------------
URL: ``BROLL_COMFYUI_URL`` env var (e.g. ``http://10.0.0.5:8188``). Defaults
to ``http://localhost:8188`` for local dev.

Timeouts: ComfyUI returns ``/prompt`` synchronously (~100 ms) but the actual
generation runs async. The polling loop waits up to
``BROLL_COMFYUI_JOB_TIMEOUT_SEC`` seconds (default 600 = 10 min — plenty for
a 5-second LTX-2.3 clip on H100 spot).

Spot interrupt recovery
-----------------------
The wrapping AI source (see :mod:`broll.sources._ai_base`) re-submits the
whole job when a spot instance dies; this client's job is to detect the
failure cleanly. Transport errors during polling are retried with
exponential backoff up to ``submit/poll_retries``; if every retry fails we
raise :class:`ComfyJobError` and let the caller decide whether to retry
the whole workflow.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import BrollError

log = logging.getLogger("broll.comfyui_client")

_DEFAULT_URL = "http://localhost:8188"
_DEFAULT_JOB_TIMEOUT = 600  # seconds end-to-end
_DEFAULT_POLL_INTERVAL = 1.5
_DEFAULT_SUBMIT_TIMEOUT = 30
_DEFAULT_DOWNLOAD_TIMEOUT = 120


class ComfyJobError(BrollError):
    """ComfyUI rejected the workflow, timed out, or the connection died.

    Distinct from ``BrollError`` so the AI source can recognize generation
    failures specifically (versus, e.g., asset_wrapper failures during
    finalize).
    """


@dataclass(slots=True)
class ComfyOutputFile:
    """One file produced by a completed ComfyUI workflow."""

    filename: str
    subfolder: str
    type: str  # "output" | "temp" | "input"
    node_id: str  # node that produced it
    mime_hint: str | None = None


@dataclass(slots=True)
class ComfyJobResult:
    """Everything a caller needs to materialize the generation artifact."""

    prompt_id: str
    files: list[ComfyOutputFile] = field(default_factory=list)
    raw_history: dict[str, Any] | None = None

    def primary_video(self) -> ComfyOutputFile | None:
        """Best guess for the user-facing video output."""
        if not self.files:
            return None
        video_exts = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
        for f in self.files:
            if f.filename.lower().endswith(video_exts):
                return f
        return self.files[-1]

    def primary_image(self) -> ComfyOutputFile | None:
        """Best guess for a still image output (SaveImage, etc.)."""
        if not self.files:
            return None
        image_exts = (".png", ".jpg", ".jpeg", ".webp")
        for f in self.files:
            if f.filename.lower().endswith(image_exts):
                return f
        return self.files[-1]


class ComfyUIClient:
    """Thin, synchronous client for one ComfyUI server."""

    def __init__(
        self,
        url: str | None = None,
        *,
        client_id: str | None = None,
        submit_timeout: float = _DEFAULT_SUBMIT_TIMEOUT,
        download_timeout: float = _DEFAULT_DOWNLOAD_TIMEOUT,
        job_timeout: float | None = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.url = (url or os.environ.get("BROLL_COMFYUI_URL") or _DEFAULT_URL).rstrip("/")
        self.client_id = client_id or f"geopoai-broll-{uuid.uuid4().hex[:12]}"
        self.submit_timeout = submit_timeout
        self.download_timeout = download_timeout
        self.job_timeout = job_timeout if job_timeout is not None else float(
            os.environ.get("BROLL_COMFYUI_JOB_TIMEOUT_SEC", _DEFAULT_JOB_TIMEOUT)
        )
        self.poll_interval = poll_interval

    def upload_image(self, image_path: Path, *, subfolder: str = "") -> dict[str, Any]:
        """Upload a local image to ComfyUI ``input/`` for LoadImage nodes."""
        import mimetypes

        path = Path(image_path)
        if not path.is_file():
            raise ComfyJobError(f"upload_image: not a file: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = f"----geopoai{uuid.uuid4().hex}"
        body_start = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        body_end = (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="subfolder"\r\n\r\n'
            f"{subfolder}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        body = body_start + path.read_bytes() + body_end
        req = urllib.request.Request(
            f"{self.url}/upload/image",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "GeoPoAI-broll/0.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.download_timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise ComfyJobError(f"comfyui upload_image failed: {exc}") from exc

    # ── HTTP primitives ─────────────────────────────────────────────────────
    def _post_json(self, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GeoPoAI-broll/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_json(self, path: str, *, timeout: float) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.url}{path}",
            headers={"User-Agent": "GeoPoAI-broll/0.1"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── Public ──────────────────────────────────────────────────────────────
    def submit(self, workflow: dict[str, Any], *, retries: int = 2) -> str:
        """Submit a workflow graph and return its ``prompt_id``.

        Retries on transport failure (the instance may still be warming the
        model into VRAM). Raises :class:`ComfyJobError` if the server
        reports node-level validation errors in the response.
        """
        payload = {"prompt": workflow, "client_id": self.client_id}
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._post_json("/prompt", payload, timeout=self.submit_timeout)
                node_errors = resp.get("node_errors") or {}
                if node_errors:
                    raise ComfyJobError(
                        f"ComfyUI rejected workflow with node_errors={node_errors}"
                    )
                prompt_id = resp.get("prompt_id")
                if not prompt_id:
                    raise ComfyJobError(f"ComfyUI response missing prompt_id: {resp}")
                log.info("comfyui submit OK prompt_id=%s url=%s", prompt_id, self.url)
                return str(prompt_id)
            except urllib.error.URLError as exc:
                last_exc = exc
                if attempt < retries:
                    sleep_for = 1.5 * (attempt + 1)
                    log.warning("comfyui submit failed (%s); retry in %.1fs", exc, sleep_for)
                    time.sleep(sleep_for)
                    continue
                raise ComfyJobError(f"comfyui submit failed after {retries + 1} attempts: {exc}") from exc
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:400] if exc.fp else ""
                raise ComfyJobError(f"comfyui HTTP {exc.code} on submit: {body}") from exc
        # Defensive — unreachable in practice.
        raise ComfyJobError(f"comfyui submit failed: {last_exc}")

    def poll_until_done(self, prompt_id: str) -> dict[str, Any]:
        """Block until the job completes; return its history record.

        Polls ``/history/<prompt_id>`` at ``self.poll_interval`` seconds.
        Tolerates transient transport errors (≥3 consecutive failures are
        fatal). Aborts after ``self.job_timeout`` seconds.
        """
        deadline = time.monotonic() + self.job_timeout
        consecutive_transport_errors = 0
        while True:
            now = time.monotonic()
            if now >= deadline:
                raise ComfyJobError(
                    f"comfyui job {prompt_id} timed out after {self.job_timeout}s"
                )
            try:
                history = self._get_json(f"/history/{prompt_id}", timeout=self.submit_timeout)
                consecutive_transport_errors = 0
            except urllib.error.URLError as exc:
                consecutive_transport_errors += 1
                log.warning(
                    "comfyui poll transport error %d/3: %s",
                    consecutive_transport_errors, exc,
                )
                if consecutive_transport_errors >= 3:
                    raise ComfyJobError(
                        f"comfyui poll failed (transport): {exc} — likely a spot interrupt"
                    ) from exc
                time.sleep(self.poll_interval)
                continue
            except urllib.error.HTTPError as exc:
                # 404 during the first ~second is normal — history not registered yet.
                if exc.code == 404:
                    time.sleep(self.poll_interval)
                    continue
                raise ComfyJobError(f"comfyui poll HTTP {exc.code}") from exc

            entry = history.get(prompt_id)
            if not entry:
                time.sleep(self.poll_interval)
                continue

            status = (entry.get("status") or {})
            # ComfyUI may leave completed=false while recording execution_error.
            for msg in status.get("messages", []) or []:
                if isinstance(msg, list) and msg and msg[0] == "execution_error":
                    detail = msg[1] if len(msg) > 1 else msg
                    if isinstance(detail, dict):
                        detail = detail.get("exception_message") or detail
                    raise ComfyJobError(
                        f"comfyui execution_error on job {prompt_id}: {detail}"
                    )
            if status.get("status_str") == "error" and not status.get("completed"):
                raise ComfyJobError(
                    f"comfyui job {prompt_id} failed (status_str=error, completed=false)"
                )

            if status.get("completed"):
                if status.get("status_str") and status["status_str"] not in (None, "success"):
                    raise ComfyJobError(
                        f"comfyui job {prompt_id} ended with status_str={status['status_str']}"
                    )
                # Some versions of ComfyUI report errors via "messages" array.
                for msg in status.get("messages", []) or []:
                    if isinstance(msg, list) and msg and msg[0] == "execution_error":
                        raise ComfyJobError(f"comfyui execution_error: {msg[1:]}")
                return entry
            time.sleep(self.poll_interval)

    def extract_outputs(self, history_entry: dict[str, Any]) -> list[ComfyOutputFile]:
        """Walk the ``outputs`` block of a history entry, normalize file refs.

        ComfyUI output nodes (SaveImage, VHS_VideoCombine, SaveAnimatedWEBP,
        custom video savers) each surface a slightly different schema. We
        normalize to a flat list of ``ComfyOutputFile``.
        """
        outputs = history_entry.get("outputs") or {}
        files: list[ComfyOutputFile] = []
        for node_id, payload in outputs.items():
            if not isinstance(payload, dict):
                continue
            # Common keys across savers.
            for key in ("images", "gifs", "videos", "files"):
                items = payload.get(key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    filename = item.get("filename")
                    if not filename:
                        continue
                    files.append(
                        ComfyOutputFile(
                            filename=filename,
                            subfolder=item.get("subfolder", "") or "",
                            type=item.get("type", "output") or "output",
                            node_id=str(node_id),
                            mime_hint=item.get("format"),
                        )
                    )
        return files

    def download(self, output: ComfyOutputFile, target_path: Path) -> Path:
        """Stream ``/view`` into ``target_path``. Atomic via sibling temp."""
        params = urllib.parse.urlencode({
            "filename": output.filename,
            "subfolder": output.subfolder,
            "type": output.type,
        })
        url = f"{self.url}/view?{params}"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = target_path.with_suffix(target_path.suffix + ".tmp")
        req = urllib.request.Request(url, headers={"User-Agent": "GeoPoAI-broll/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=self.download_timeout) as resp, tmp.open("wb") as fp:
                shutil.copyfileobj(resp, fp, length=1 << 16)
            os.replace(tmp, target_path)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise ComfyJobError(f"comfyui download failed for {output.filename}: {exc}") from exc
        return target_path

    # ── Convenience ─────────────────────────────────────────────────────────
    def run(
        self,
        workflow: dict[str, Any],
        *,
        download_to: Path | None = None,
        prefer_image: bool = False,
    ) -> ComfyJobResult:
        """Submit, poll, extract — and optionally download the primary artifact."""
        prompt_id = self.submit(workflow)
        history = self.poll_until_done(prompt_id)
        files = self.extract_outputs(history)
        result = ComfyJobResult(prompt_id=prompt_id, files=files, raw_history=history)
        if download_to is not None:
            primary = result.primary_image() if prefer_image else result.primary_video()
            if primary is None:
                primary = result.primary_video() or result.primary_image()
            if primary is None:
                raise ComfyJobError(
                    f"comfyui job {prompt_id} completed but produced no recognizable output file"
                )
            self.download(primary, download_to)
        return result

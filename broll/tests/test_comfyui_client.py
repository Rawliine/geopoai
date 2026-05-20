"""ComfyUI client: submit, poll, download — against the mock server."""

from __future__ import annotations

from pathlib import Path

import pytest

from broll.lib.comfyui_client import ComfyJobError, ComfyUIClient

from . import _comfyui_mock as mock


@pytest.fixture
def comfy_url():
    server, thread, url = mock.start()
    try:
        yield url
    finally:
        mock.stop(server, thread)


def test_submit_and_poll_happy_path(comfy_url, tmp_path: Path) -> None:
    client = ComfyUIClient(comfy_url, poll_interval=0.05)
    result = client.run({"some": "workflow"}, download_to=tmp_path / "out.mp4")
    assert (tmp_path / "out.mp4").exists()
    assert result.primary_video() is not None
    assert result.primary_video().filename.startswith("broll_")


def test_submit_failure_retries_then_raises(comfy_url) -> None:
    mock.MockComfy.fail_on_submit = True
    client = ComfyUIClient(comfy_url, submit_timeout=2, poll_interval=0.05)
    with pytest.raises(ComfyJobError):
        client.submit({"workflow": True}, retries=0)


def test_poll_tolerates_transient_transport_errors(comfy_url, tmp_path: Path) -> None:
    mock.MockComfy.fail_n_polls = 2  # < 3 (the consecutive-failure cap)
    client = ComfyUIClient(comfy_url, poll_interval=0.05)
    result = client.run({"workflow": True}, download_to=tmp_path / "out.mp4")
    assert (tmp_path / "out.mp4").exists()
    assert result.prompt_id


def test_node_errors_surface_as_jobError(comfy_url) -> None:
    mock.MockComfy.node_errors = {"5": "missing input"}
    client = ComfyUIClient(comfy_url, poll_interval=0.05)
    with pytest.raises(ComfyJobError):
        client.submit({"workflow": True})


def test_execution_error_surface_as_jobError(comfy_url, tmp_path: Path) -> None:
    mock.MockComfy.execution_error = ["cuda_oom"]
    client = ComfyUIClient(comfy_url, poll_interval=0.05)
    with pytest.raises(ComfyJobError):
        client.run({"workflow": True}, download_to=tmp_path / "out.mp4")


def test_timeout(comfy_url, monkeypatch) -> None:
    # Force the client to consider any /history a "still pending" by patching
    # the mock to never complete.
    original = mock._Handler.do_GET

    def slow_get(self):  # noqa: ANN001
        if self.path.startswith("/history/"):
            # Return 404 → client treats as not-yet-registered, keeps polling.
            self.send_response(404)
            self.end_headers()
            return
        return original(self)

    monkeypatch.setattr(mock._Handler, "do_GET", slow_get)
    client = ComfyUIClient(comfy_url, job_timeout=0.5, poll_interval=0.1)
    with pytest.raises(ComfyJobError):
        client.run({"workflow": True})

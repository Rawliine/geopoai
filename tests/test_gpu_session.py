"""W19 tests: GPU session manager registry, state, idle logic, destroy safety."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from pipeline import gpu_session as gs  # noqa: E402


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
  path = tmp_path / "sessions.json"
  path.write_text((_REPO / "infra" / "sessions.json").read_text(encoding="utf-8"), encoding="utf-8")
  return path


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
  return tmp_path / ".session_state.json"


def _sample_session(workload: str = "comfyui_setup", **overrides: Any) -> dict[str, Any]:
  now = datetime(2025, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
  base = {
    "workload": workload,
    "run_id": f"{workload}-2025-06-25-1",
    "started_at": now.isoformat(),
    "last_activity_at": now.isoformat(),
    "ip": "10.0.0.5",
    "instance_id": "inst-123",
    "tfvars": ["workloads/comfyui.tfvars"],
    "gpu_type": "1V100.6V",
  }
  base.update(overrides)
  return base


def test_registry_parses_all_workloads(registry_path: Path) -> None:
  rates, workloads = gs.load_registry(registry_path)
  assert set(workloads) == {"comfyui", "comfyui_setup", "blender_render", "lora_train"}
  assert workloads["comfyui"].health.type == "http"
  assert workloads["blender_render"].health.type == "ssh"
  assert rates["1H100.80S.30V"] == 0.80


def test_state_lifecycle(state_path: Path) -> None:
  state: dict[str, dict[str, Any]] = {}
  session = _sample_session()
  state["comfyui_setup"] = session
  gs.save_state(state, state_path)
  loaded = gs.load_state(state_path)
  assert loaded["comfyui_setup"]["run_id"] == session["run_id"]

  gs.record_activity("comfyui_setup", path=state_path)
  updated = gs.load_state(state_path)["comfyui_setup"]
  assert updated["last_activity_at"] != session["last_activity_at"]

  state.pop("comfyui_setup")
  gs.save_state(state, state_path)
  assert gs.load_state(state_path) == {}


def test_generate_run_id_increments(state_path: Path) -> None:
  state = {"comfyui_setup": _sample_session(run_id="comfyui_setup-2025-06-25-1")}
  gs.save_state(state, state_path)
  with mock.patch.object(gs, "_utc_now", return_value=datetime(2025, 6, 25, 9, 0, tzinfo=timezone.utc)):
    rid = gs.generate_run_id("comfyui_setup", gs.load_state(state_path))
  assert rid == "comfyui_setup-2025-06-25-2"


def test_cost_math() -> None:
  session = _sample_session()
  rates = {"1V100.6V": 0.35}
  now = datetime(2025, 6, 25, 14, 0, 0, tzinfo=timezone.utc)
  cost = gs.estimate_cost_usd(session, rates, now=now)
  assert cost == pytest.approx(0.70, rel=1e-3)


def test_should_teardown_idle(registry_path: Path) -> None:
  _, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  started = datetime(2025, 6, 25, 10, 0, 0, tzinfo=timezone.utc)
  last = started
  session = _sample_session(started_at=started.isoformat(), last_activity_at=last.isoformat())
  now = started + timedelta(minutes=61)
  with mock.patch.object(gs, "detect_activity", return_value=(False, "fp")):
    teardown, reason = gs.should_teardown(session, workload, now=now)
  assert teardown is True
  assert "IDLE" in reason


def test_should_teardown_hard_cap(registry_path: Path) -> None:
  _, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  started = datetime(2025, 6, 25, 10, 0, 0, tzinfo=timezone.utc)
  session = _sample_session(started_at=started.isoformat())
  now = started + timedelta(hours=7)
  teardown, reason = gs.should_teardown(session, workload, now=now)
  assert teardown is True
  assert "HARD BUDGET CAP" in reason


def test_destroy_targets_instance_only(registry_path: Path) -> None:
  _, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  args = gs.terraform_destroy_args(workload, "test-run-001")
  assert "-target=verda_instance.this" in args
  assert not any("verda_volume" in a for a in args)


def test_run_terraform_never_passes_volume(monkeypatch: pytest.MonkeyPatch, registry_path: Path) -> None:
  captured: list[list[str]] = []

  def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    captured.append(cmd)
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

  monkeypatch.setattr(gs.subprocess, "run", fake_run)
  _, workloads = gs.load_registry(registry_path)
  gs.run_terraform(gs.terraform_destroy_args(workloads["comfyui_setup"], "rid-1"))
  assert captured
  joined = " ".join(captured[0])
  assert "verda_instance.this" in joined
  assert "verda_volume" not in joined


def test_cmd_up_refuses_live_duplicate(
  registry_path: Path,
  state_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  rates, workloads = gs.load_registry(registry_path)
  session = _sample_session()
  gs.save_state({"comfyui_setup": session}, state_path)
  monkeypatch.setattr(gs, "_STATE_PATH", state_path)
  monkeypatch.setattr(gs, "is_session_live", lambda s, w: True)
  ns = mock.Mock(workload="comfyui_setup", run_id="auto", verbose=False)
  rc = gs.cmd_up(ns, rates, workloads)
  assert rc == 1


def test_watchdog_teardown_calls_down(
  registry_path: Path,
  state_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  workload_name = "comfyui_setup"
  session = _sample_session()
  gs.save_state({workload_name: session}, state_path)

  monkeypatch.setattr(
    gs,
    "should_teardown",
    lambda *a, **k: (True, "IDLE test"),
  )
  monkeypatch.setattr(gs, "detect_activity", lambda *a, **k: (False, "fp"))
  monkeypatch.setattr(gs, "cmd_down", lambda *a, **k: 0)

  rc = gs.watchdog_loop(workload_name, poll_sec=1, state_path=state_path, once=True)
  assert rc == 0


def test_poll_comfyui_activity_detects_queue() -> None:
  queue_body = json.dumps({"queue_running": [["id", 1]], "queue_pending": []}).encode()

  class FakeResp:
    def __enter__(self):
      return self

    def __exit__(self, *args: Any) -> None:
      return None

    def read(self) -> bytes:
      return queue_body

  with mock.patch("urllib.request.urlopen", side_effect=[FakeResp(), FakeResp()]):
    active, _ = gs.poll_comfyui_activity("10.0.0.5")
  assert active is True

"""W19/W23 tests: GPU session manager registry, state, idle, interactive wizard."""

from __future__ import annotations

import argparse
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
  rates, profiles, workloads = gs.load_registry(registry_path)
  assert set(workloads) == {"comfyui", "comfyui_setup", "blender_render", "lora_train"}
  assert workloads["comfyui"].health.type == "http"
  assert workloads["blender_render"].health.type == "ssh"
  assert "h100_spot" in profiles
  assert profiles["h100_spot"].instance_type == "1H100.80S.30V"
  assert workloads["comfyui"].gpu_preference[0] == "h100_spot"


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
  _, _, workloads = gs.load_registry(registry_path)
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
  _, _, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  started = datetime(2025, 6, 25, 10, 0, 0, tzinfo=timezone.utc)
  session = _sample_session(started_at=started.isoformat())
  now = started + timedelta(hours=7)
  teardown, reason = gs.should_teardown(session, workload, now=now)
  assert teardown is True
  assert "HARD BUDGET CAP" in reason


def test_destroy_targets_instance_only(registry_path: Path) -> None:
  _, _, workloads = gs.load_registry(registry_path)
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
  _, _, workloads = gs.load_registry(registry_path)
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
  rates, profiles, workloads = gs.load_registry(registry_path)
  session = _sample_session()
  gs.save_state({"comfyui_setup": session}, state_path)
  monkeypatch.setattr(gs, "_STATE_PATH", state_path)
  monkeypatch.setattr(gs, "is_session_live", lambda s, w, gp=None: True)
  ns = mock.Mock(workload="comfyui_setup", run_id="auto", verbose=False, profile=None)
  rc = gs.cmd_up(ns, rates, profiles, workloads)
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


def test_is_capacity_error_detects_503() -> None:
  result = subprocess.CompletedProcess([], 1, "", '{"code":"service_unavailable","message":"Not enough resources"}')
  assert gs.is_service_unavailable(result) is True


def test_resolve_verda_image_from_supported_os() -> None:
  entry = {
    "instance_type": "1V100.6V",
    "supported_os": ["ubuntu-22.04-cuda-12.4-docker", "ubuntu-24.04"],
  }
  assert gs.resolve_verda_image(entry) == "ubuntu-22.04-cuda-13.0-open-docker" or (
    gs.resolve_verda_image(entry) == "ubuntu-22.04-cuda-12.4-docker"
  )
  assert gs.resolve_verda_image(entry, ("ubuntu-22.04-cuda-12.4-docker",)) == "ubuntu-22.04-cuda-12.4-docker"


def test_apply_with_gpu_fallback_tries_next_profile(registry_path: Path) -> None:
  _, profiles, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  catalog = {
    p.instance_type: {"instance_type": p.instance_type, "supported_os": ["ubuntu-22.04-cuda-12.4-docker"]}
    for p in gs.profiles_to_try(workload, profiles)
  }
  chain = gs.resolve_profiles_for_location(
    gs.profiles_to_try(workload, profiles)[:2],
    catalog,
    "FIN-01",
    None,
  )
  calls: list[str] = []

  def fake_run(tf_args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    joined = " ".join(tf_args)
    if "apply" in tf_args:
      for p in chain:
        if p.instance_type in joined:
          calls.append(p.name)
          break
    if len(calls) == 1:
      return subprocess.CompletedProcess(tf_args, 1, "", '{"code":"service_unavailable"}')
    return subprocess.CompletedProcess(tf_args, 0, "", "")

  with mock.patch.object(gs, "run_terraform", side_effect=fake_run):
    chosen, _ = gs.apply_with_gpu_fallback(workload, "test-run", chain)
  assert chosen == chain[1]
  assert calls == [chain[0].name, chain[1].name]


def test_load_storage_config(registry_path: Path) -> None:
  storage = gs.load_storage_config(registry_path)
  assert storage.models_marker.endswith(".geopoai_download_complete")
  assert storage.default_volume_size_gb == 280
  assert storage.volume_monthly_usd_per_gb == 0.10


def test_build_gpu_offerings_free_skus_only() -> None:
  catalog = [
    {
      "instance_type": "1V100.6V",
      "display_name": "V100",
      "price_per_hour": 0.17,
      "spot_price": 0.08,
      "gpu_memory": {"size_in_gigabytes": 16},
      "supported_os": ["ubuntu-22.04-cuda-12.4-docker"],
    },
    {
      "instance_type": "CPU.4V.16G",
      "display_name": "CPU",
      "price_per_hour": 0.03,
      "gpu_memory": {"size_in_gigabytes": 0},
      "supported_os": ["ubuntu-22.04"],
    },
    {
      "instance_type": "1H100.80S.30V",
      "display_name": "H100",
      "price_per_hour": 2.5,
      "spot_price": 1.0,
      "gpu_memory": {"size_in_gigabytes": 80},
      "supported_os": ["ubuntu-24.04-cuda-13.0-open-docker"],
    },
  ]
  availability = {"FIN-01": {"1V100.6V"}, "FIN-03": {"1H100.80S.30V", "CPU.4V.16G"}}
  rows = gs.build_gpu_offerings(catalog, availability)
  types = {(r.location, r.instance_type) for r in rows}
  assert ("FIN-01", "1V100.6V") in types
  assert ("FIN-03", "1H100.80S.30V") in types
  assert not any(r.instance_type.startswith("CPU.") for r in rows)
  assert rows[0].price_ondemand == 0.17


def test_build_gpu_offerings_include_cpu() -> None:
  catalog = [{"instance_type": "CPU.4V.16G", "price_per_hour": 0.03, "gpu_memory": {}}]
  availability = {"FIN-03": {"CPU.4V.16G"}}
  rows = gs.build_gpu_offerings(catalog, availability, include_cpu=True)
  assert len(rows) == 1


def test_offering_to_profile() -> None:
  offering = gs.GpuOffering(
    location="FIN-03",
    instance_type="1V100.6V",
    display_name="V100",
    vram_gb=16.0,
    price_ondemand=0.17,
    price_spot=0.08,
    supported_os=("ubuntu-22.04-cuda-12.4-docker",),
  )
  profile = gs.offering_to_profile(offering, use_spot=False)
  assert profile.location == "FIN-03"
  assert profile.instance_type == "1V100.6V"
  assert profile.verda_image == "ubuntu-22.04-cuda-12.4-docker"


def test_cmd_destroy_volume_refuses_live_instance(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(gs, "instance_in_terraform_state", lambda: True)
  rates, profiles, workloads = gs.load_registry()
  rc = gs.cmd_destroy_volume(
    argparse.Namespace(),
    rates,
    profiles,
    workloads,
    input_fn=lambda _: "yes",
  )
  assert rc == 1


def test_cmd_destroy_volume_requires_name_confirm(
  monkeypatch: pytest.MonkeyPatch,
  registry_path: Path,
) -> None:
  vol = gs.VolumeState(
    id="vol-1",
    name="geopoai-models-persistent",
    location="FIN-03",
    size_gb=280,
    status="detached",
    monthly_cost_estimate=28.0,
    in_terraform_state=True,
  )
  monkeypatch.setattr(gs, "instance_in_terraform_state", lambda: False)
  monkeypatch.setattr(gs, "load_state", lambda: {})
  monkeypatch.setattr(gs, "verda_oauth_token", lambda: "tok")
  monkeypatch.setattr(gs, "read_volume_state", lambda *a, **k: vol)
  deleted: list[str] = []
  monkeypatch.setattr(gs, "verda_api_delete", lambda path, **k: deleted.append(path))
  monkeypatch.setattr(
    gs,
    "run_terraform",
    lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""),
  )
  rates, profiles, workloads = gs.load_registry(registry_path)
  inputs = iter(["yes", "wrong-name"])
  rc = gs.cmd_destroy_volume(
    argparse.Namespace(),
    rates,
    profiles,
    workloads,
    input_fn=lambda _: next(inputs),
  )
  assert rc == 1
  assert deleted == []

  inputs2 = iter(["yes", "geopoai-models-persistent"])
  rc2 = gs.cmd_destroy_volume(
    argparse.Namespace(),
    rates,
    profiles,
    workloads,
    input_fn=lambda _: next(inputs2),
  )
  assert rc2 == 0
  assert deleted == ["volumes/vol-1"]


def test_prompt_download_skips_when_marker(
  registry_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  _, profiles, workloads = gs.load_registry(registry_path)
  workload = workloads["comfyui_setup"]
  storage = gs.load_storage_config(registry_path)
  session = _sample_session()
  profile = gs.profile_for_session(session, profiles)
  monkeypatch.setattr(gs, "models_download_complete", lambda ip, marker: True)
  called = []
  monkeypatch.setattr(gs, "run_download_on_vm", lambda *a, **k: called.append(1) or 0)
  rc = gs.prompt_download_if_needed(session, workload, profile, storage, input_fn=lambda _: "y")
  assert rc == 0
  assert called == []


def test_cmd_interactive_aborts_without_tty(
  registry_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  rates, profiles, workloads = gs.load_registry(registry_path)
  monkeypatch.setattr(gs, "_is_tty", lambda: False)
  ns = argparse.Namespace(workload=None, teardown=False, verbose=False, force=False)
  rc = gs.cmd_interactive(ns, rates, profiles, workloads)
  assert rc == 1


def test_cmd_setup_requires_session(registry_path: Path) -> None:
  rates, profiles, workloads = gs.load_registry(registry_path)
  ns = argparse.Namespace(workload="comfyui_setup", yes=False)
  with mock.patch.object(gs, "load_state", return_value={}):
    rc = gs.cmd_setup(ns, rates, profiles, workloads)
  assert rc == 1


def test_cost_prefers_session_hourly_rate() -> None:
  # Registry rate table is empty in production; the rate captured at deploy time wins.
  session = _sample_session(hourly_usd=2.0)
  now = datetime(2025, 6, 25, 14, 0, 0, tzinfo=timezone.utc)
  assert gs.estimate_cost_usd(session, {}, now=now) == pytest.approx(4.0, rel=1e-3)


def test_hourly_rate_for_profile_spot_vs_ondemand() -> None:
  catalog = {"1V100.6V": {"instance_type": "1V100.6V", "price_per_hour": 0.17, "spot_price": 0.08}}
  od = gs.GpuProfile(name="x", instance_type="1V100.6V", use_spot=False, label="")
  spot = gs.GpuProfile(name="x", instance_type="1V100.6V", use_spot=True, label="")
  assert gs.hourly_rate_for_profile(od, catalog) == 0.17
  assert gs.hourly_rate_for_profile(spot, catalog) == 0.08
  assert gs.hourly_rate_for_profile(od, {}) is None


def test_run_subcommand_does_not_clobber_command_dest() -> None:
  ns = gs.build_parser().parse_args(["run", "comfyui", "--", "echo", "hi"])
  assert ns.command == "run"
  assert gs._normalize_run_command(ns.cmd) == ["echo", "hi"]

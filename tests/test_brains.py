"""Tests for the swappable brain layer (W24)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brains.api import AnthropicProvider, ApiBrain, ProviderResponse, make_api_brain  # noqa: E402
from brains.base import (  # noqa: E402
    AwaitingBrainError,
    Brain,
    BrainResult,
    BrainValidationError,
    validate_and_repair,
)
from brains.cli_agent import CliAgentBrain, extract_first_json_object, make_cli_brain  # noqa: E402
from brains.halt import HaltBrain  # noqa: E402
from brains.select import select_brain  # noqa: E402

TRIVIAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["message"],
    "additionalProperties": False,
    "properties": {"message": {"type": "string", "minLength": 1}},
}

GOOD_ARTIFACT = {"message": "hello from brain"}


class _RecordingBrain:
    name = "recording"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def author(self, instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(instruction)
        if not self._responses:
            raise RuntimeError("no more scripted responses")
        return self._responses.pop(0)


def test_extract_first_json_object_from_wrapper() -> None:
    wrapped = json.dumps({"result": json.dumps(GOOD_ARTIFACT)})
    assert extract_first_json_object(wrapped) == GOOD_ARTIFACT


def test_extract_first_json_object_from_embedded_text() -> None:
    text = f"Here is the artifact:\n{json.dumps(GOOD_ARTIFACT)}\nThanks."
    assert extract_first_json_object(text) == GOOD_ARTIFACT


# ── Protocol conformance ─────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["halt", "claude-cli", "gemini-cli", "api"])
def test_select_brain_resolves_known_names(name: str) -> None:
    if name == "api":
        provider = MagicMock(spec=AnthropicProvider)
        provider.name = "anthropic"
        provider.model = "claude-sonnet-4-6"
        provider.temperature = 0.0
        brain = make_api_brain(provider_instance=provider)
    else:
        brain = select_brain(name)
    assert isinstance(brain, Brain)


def test_select_brain_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown brain"):
        select_brain("not-a-brain")


def test_halt_brain_writes_stage_files_and_awaits(tmp_path: Path) -> None:
    brain = HaltBrain()
    result = validate_and_repair(
        brain,
        "Write a greeting.",
        TRIVIAL_SCHEMA,
        {"stage_dir": str(tmp_path)},
    )
    assert result.awaiting is True
    assert result.artifact is None
    assert result.brain == "halt"
    assert (tmp_path / "instruction.md").read_text(encoding="utf-8").startswith("Write a greeting.")
    assert json.loads((tmp_path / "schema.json").read_text(encoding="utf-8")) == TRIVIAL_SCHEMA


def test_cli_agent_brain_authors_via_mocked_subprocess() -> None:
    payload = json.dumps({"result": json.dumps(GOOD_ARTIFACT)})

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "/usr/bin/claude"
        assert "-p" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")

    brain = CliAgentBrain(
        command_key="claude_cli",
        command_template=["claude", "-p", "{prompt}", "--output-format", "json"],
        binary_resolver=lambda _: "/usr/bin/claude",
        runner=fake_run,
    )
    artifact = brain.author("say hello", TRIVIAL_SCHEMA, {"episode_id": "ep001"})
    assert artifact == GOOD_ARTIFACT


def test_api_brain_authors_via_mocked_provider() -> None:
    provider = MagicMock(spec=AnthropicProvider)
    provider.name = "anthropic"
    provider.model = "claude-sonnet-4-6"
    provider.temperature = 0.0
    provider.complete.return_value = ProviderResponse(
        text=json.dumps(GOOD_ARTIFACT),
        input_tokens=120,
        output_tokens=30,
        model="claude-sonnet-4-6",
        provider="anthropic",
    )

    brain = ApiBrain(provider=provider, max_repairs=0)
    context: dict[str, Any] = {}
    artifact = brain.author("say hello", TRIVIAL_SCHEMA, context)

    assert artifact == GOOD_ARTIFACT
    assert provider.complete.call_count == 1
    assert context["_brain_usage"]["total_tokens"] == 150
    assert context["_brain_usage"]["cost_usd"] > 0


# ── validate_and_repair ──────────────────────────────────────────────────────
def test_validate_and_repair_happy_path() -> None:
    brain = _RecordingBrain([GOOD_ARTIFACT])
    result = validate_and_repair(brain, "author greeting", TRIVIAL_SCHEMA, {})
    assert result == BrainResult(
        artifact=GOOD_ARTIFACT,
        brain="recording",
        attempts=1,
        awaiting=False,
        tokens=None,
        cost_usd=None,
        usage={},
    )


def test_validate_and_repair_repairs_invalid_first_attempt() -> None:
    brain = _RecordingBrain([{"message": ""}, GOOD_ARTIFACT])
    result = validate_and_repair(brain, "author greeting", TRIVIAL_SCHEMA, {}, max_repairs=2)

    assert result.artifact == GOOD_ARTIFACT
    assert result.attempts == 2
    assert len(brain.calls) == 2
    assert "failed schema validation" in brain.calls[1]


def test_validate_and_repair_raises_after_max_repairs() -> None:
    brain = _RecordingBrain([{"message": ""}, {"message": ""}, {"message": ""}])
    with pytest.raises(BrainValidationError, match="failed schema validation"):
        validate_and_repair(brain, "author greeting", TRIVIAL_SCHEMA, {}, max_repairs=1)


def test_api_brain_internal_repair_loop_fixes_invalid_first_attempt() -> None:
    provider = MagicMock(spec=AnthropicProvider)
    provider.name = "anthropic"
    provider.model = "claude-sonnet-4-6"
    provider.temperature = 0.0
    provider.complete.side_effect = [
        ProviderResponse(
            text=json.dumps({"message": ""}),
            input_tokens=50,
            output_tokens=10,
            model="claude-sonnet-4-6",
            provider="anthropic",
        ),
        ProviderResponse(
            text=json.dumps(GOOD_ARTIFACT),
            input_tokens=80,
            output_tokens=20,
            model="claude-sonnet-4-6",
            provider="anthropic",
        ),
    ]

    brain = ApiBrain(provider=provider, max_repairs=2)
    artifact = brain.author("say hello", TRIVIAL_SCHEMA, {})

    assert artifact == GOOD_ARTIFACT
    assert provider.complete.call_count == 2
    second_prompt = provider.complete.call_args_list[1].args[0]
    assert "failed schema validation" in second_prompt


# ── Acceptance: each brain authors trivial artifact (mocked where needed) ──
def test_select_halt_awaits_operator(tmp_path: Path) -> None:
    result = validate_and_repair(
        select_brain("halt"),
        "author greeting",
        TRIVIAL_SCHEMA,
        {"stage_dir": str(tmp_path)},
    )
    assert result.awaiting is True


def test_select_claude_cli_authors_trivial_artifact() -> None:
    payload = json.dumps({"result": json.dumps(GOOD_ARTIFACT)})

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")

    brain = make_cli_brain("claude_cli")
    # monkeypatch via direct construction for deterministic binary resolution
    cli = CliAgentBrain(
        command_key="claude_cli",
        command_template=brain.command_template,
        binary_resolver=lambda _: "/usr/bin/claude",
        runner=fake_run,
    )
    result = validate_and_repair(cli, "author greeting", TRIVIAL_SCHEMA, {})
    assert result.artifact == GOOD_ARTIFACT
    assert result.awaiting is False


def test_select_api_authors_trivial_artifact_with_mock_provider() -> None:
    provider = MagicMock(spec=AnthropicProvider)
    provider.name = "anthropic"
    provider.model = "claude-sonnet-4-6"
    provider.temperature = 0.0
    provider.complete.return_value = ProviderResponse(
        text=json.dumps(GOOD_ARTIFACT),
        input_tokens=10,
        output_tokens=5,
        model="claude-sonnet-4-6",
        provider="anthropic",
    )
    brain = make_api_brain(provider_instance=provider)
    result = validate_and_repair(brain, "author greeting", TRIVIAL_SCHEMA, {})
    assert result.artifact == GOOD_ARTIFACT
    assert result.tokens == 15
    assert result.cost_usd is not None


def test_halt_author_raises_awaiting_directly() -> None:
    brain = HaltBrain()
    with pytest.raises(AwaitingBrainError):
        brain.author("x", TRIVIAL_SCHEMA, {"stage_dir": "/tmp/unused-halt"})

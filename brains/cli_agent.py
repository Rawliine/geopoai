"""CLI-agent brain — shell out to claude/gemini subscription CLIs."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .base import Brain

log = logging.getLogger("brains.cli_agent")

_DEFAULT_COMMANDS: dict[str, list[str]] = {
    "claude_cli": ["claude", "-p", "{prompt}", "--output-format", "json"],
    "gemini_cli": ["gemini", "-p", "{prompt}"],
}


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def extract_first_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object found in CLI stdout."""
    stripped = _strip_markdown_fences(text)

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            for key in ("result", "content", "text", "message"):
                val = parsed.get(key)
                if isinstance(val, str) and val.strip():
                    try:
                        return extract_first_json_object(val)
                    except ValueError:
                        continue
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start < 0:
        raise ValueError(f"no JSON object found in CLI output: {text[:300]!r}")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : i + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
                return parsed

    raise ValueError(f"unbalanced JSON object in CLI output: {text[:300]!r}")


def build_authoring_prompt(
    instruction: str,
    schema: dict[str, Any],
    context: dict[str, Any],
) -> str:
    return (
        "You are a strict JSON authoring assistant. Produce exactly one JSON object "
        "that satisfies the schema below. No prose, no markdown fences.\n\n"
        f"Instruction:\n{instruction.strip()}\n\n"
        f"JSON Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"Context:\n{json.dumps(context, indent=2)}\n"
    )


@dataclass(slots=True)
class CliAgentBrain:
    """Run a subscription CLI (claude/gemini) and parse JSON from stdout."""

    command_key: str
    command_template: list[str]
    timeout: float = 180.0
    binary_resolver: Callable[[str], str | None] = shutil.which
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    @property
    def name(self) -> str:
        return self.command_key.replace("_", "-")

    def _resolve_binary(self, template: list[str]) -> list[str]:
        binary = template[0]
        resolved = self.binary_resolver(binary)
        if not resolved:
            raise RuntimeError(f"{binary} CLI not found on PATH")
        return [resolved, *template[1:]]

    def _run_cli(self, prompt: str) -> str:
        template = [part.replace("{prompt}", prompt) for part in self.command_template]
        cmd = self._resolve_binary(template)

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fp:
            fp.write(prompt)
            prompt_path = Path(fp.name)

        try:
            log.debug("cli_agent running %s (prompt file %s)", cmd[0], prompt_path)
            proc = self.runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        finally:
            prompt_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:400]
            raise RuntimeError(f"{cmd[0]} exited {proc.returncode}: {err}")

        raw = (proc.stdout or "").strip()
        if not raw:
            raise RuntimeError(f"{cmd[0]} produced empty stdout")
        return raw

    def author(self, instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        prompt = build_authoring_prompt(instruction, schema, context)
        raw = self._run_cli(prompt)
        return extract_first_json_object(raw)


def make_cli_brain(
    command_key: str,
    *,
    command_template: list[str] | None = None,
    timeout: float = 180.0,
) -> CliAgentBrain:
    template = command_template or _DEFAULT_COMMANDS.get(command_key)
    if not template:
        raise ValueError(f"unknown cli command key {command_key!r}")
    return CliAgentBrain(command_key=command_key, command_template=template, timeout=timeout)

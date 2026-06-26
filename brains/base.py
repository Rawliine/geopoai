"""Brain protocol, result carrier, and shared validate-and-repair helper."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator


class AwaitingBrainError(Exception):
    """Raised when a brain needs operator action before an artifact exists."""


class BrainValidationError(Exception):
    """Raised when an artifact cannot be validated after all repair attempts."""


@runtime_checkable
class Brain(Protocol):
    """Turn one authoring request into a candidate artifact dict."""

    @property
    def name(self) -> str: ...

    def author(self, instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(slots=True)
class BrainResult:
    """Outcome of ``validate_and_repair`` (or a direct brain run)."""

    artifact: dict[str, Any] | None
    brain: str
    attempts: int
    awaiting: bool = False
    tokens: int | None = None
    cost_usd: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def _format_validation_errors(schema: dict[str, Any], artifact: dict[str, Any]) -> str:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if not errors:
        return "unknown validation failure"
    return "\n".join(
        f"  - {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    )


def _validate_artifact(schema: dict[str, Any], artifact: dict[str, Any]) -> str | None:
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(artifact))
    if not errors:
        return None
    return _format_validation_errors(schema, artifact)


def validate_and_repair(
    brain: Brain,
    instruction: str,
    schema: dict[str, Any],
    context: dict[str, Any],
    *,
    max_repairs: int = 2,
) -> BrainResult:
    """Run ``brain.author``, validate against ``schema``, re-prompt on failure."""
    current_instruction = instruction
    usage: dict[str, Any] = {}
    tokens: int | None = None
    cost_usd: float | None = None

    for attempt in range(1, max_repairs + 2):
        try:
            artifact = brain.author(current_instruction, schema, context)
        except AwaitingBrainError:
            return BrainResult(
                artifact=None,
                brain=brain.name,
                attempts=attempt,
                awaiting=True,
                tokens=tokens,
                cost_usd=cost_usd,
                usage=usage,
            )

        brain_usage = context.get("_brain_usage")
        if isinstance(brain_usage, dict):
            usage = {**usage, **brain_usage}
            tokens = brain_usage.get("total_tokens", tokens)
            cost_usd = brain_usage.get("cost_usd", cost_usd)

        error = _validate_artifact(schema, artifact)
        if error is None:
            return BrainResult(
                artifact=artifact,
                brain=brain.name,
                attempts=attempt,
                awaiting=False,
                tokens=tokens,
                cost_usd=cost_usd,
                usage=usage,
            )

        if attempt > max_repairs:
            raise BrainValidationError(
                f"brain {brain.name!r} failed schema validation after {attempt} attempt(s):\n{error}"
            )

        current_instruction = (
            f"{instruction}\n\n"
            f"Your previous JSON response failed schema validation. Fix it and respond with "
            f"valid JSON only.\n\nValidation errors:\n{error}\n\n"
            f"Required schema:\n{json.dumps(schema, indent=2)}"
        )

    raise BrainValidationError(f"brain {brain.name!r} exhausted repair loop")

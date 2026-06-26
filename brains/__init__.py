"""Swappable authoring brains — (instruction, schema, context) → validated artifact."""

from .base import (
    AwaitingBrainError,
    Brain,
    BrainResult,
    BrainValidationError,
    validate_and_repair,
)

__all__ = [
    "AwaitingBrainError",
    "Brain",
    "BrainResult",
    "BrainValidationError",
    "validate_and_repair",
]

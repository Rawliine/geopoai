"""Episode compose orchestrator — W17 implements against compose.schema.json."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _REPO_ROOT / "docs" / "contracts" / "compose.schema.json"
_TOKENS_PATH = _REPO_ROOT / "config" / "design_tokens.json"

_BURN_IN_VALUES = frozenset({"never", "broll_only", "shorts_only", "always"})


def load_tokens(path: Path | None = None) -> dict[str, Any]:
    tokens_path = path or _TOKENS_PATH
    return json.loads(tokens_path.read_text(encoding="utf-8"))


def _schema_validate(spec: dict[str, Any]) -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    sanitized = deepcopy(spec)
    sanitized.pop("caption_policy", None)
    for clip in sanitized.get("clips", []):
        clip.pop("renderer", None)
        clip.pop("captions", None)
    jsonschema.validate(instance=sanitized, schema=schema)


def parse_caption_policy(spec: dict[str, Any]) -> dict[str, Any]:
    """Return normalized caption policy with defaults."""
    raw = spec.get("caption_policy")
    if raw is None:
        policy = {"burn_in": "broll_only", "sidecar": False}
    elif isinstance(raw, dict):
        policy = {
            "burn_in": raw.get("burn_in", "broll_only"),
            "sidecar": bool(raw.get("sidecar", False)),
        }
    else:
        raise ValueError("caption_policy must be an object when present")

    if policy["burn_in"] not in _BURN_IN_VALUES:
        raise ValueError(f"unsupported caption_policy.burn_in: {policy['burn_in']!r}")

    if spec.get("flags", {}).get("captions") is False:
        policy = {**policy, "burn_in": "never"}
    return policy


def validate_spec(spec: dict[str, Any]) -> None:
    """Validate compose spec against schema plus relaxed caption_policy."""
    _schema_validate(spec)
    parse_caption_policy(spec)


def compose(
    compose_spec: dict[str, Any],
    workdir: Path,
    **kwargs: Any,
) -> dict[str, Path]:
    """Assemble clips per *compose_spec* into per-profile final MP4s."""
    validate_spec(compose_spec)
    raise NotImplementedError("composition.engine.compose pass pipeline is implemented in W17.T3")

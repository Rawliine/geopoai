#!/usr/bin/env python3
"""Validate docs/contracts/fixtures/*.min.json against their schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parent.parent
_FIXTURES = _ROOT / "docs" / "contracts" / "fixtures"
_SCHEMAS = _ROOT / "docs" / "contracts"

_PAIRS = [
    ("events.min.json", "events.schema.json"),
    ("layout.min.json", "layout.schema.json"),
    ("episode.min.json", "episode.schema.json"),
    ("compose.min.json", "compose.schema.json"),
    ("asset_manifest.min.json", "asset_manifest.schema.json"),
]


def main() -> int:
    errors: list[str] = []
    for fixture_name, schema_name in _PAIRS:
        schema = json.loads((_SCHEMAS / schema_name).read_text(encoding="utf-8"))
        data = json.loads((_FIXTURES / fixture_name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            errors.append(f"{fixture_name}: {err.message} at {list(err.path)}")
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print(f"validated {len(_PAIRS)} fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

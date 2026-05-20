"""CI guard: enforce that nothing under ``broll/`` (except asset_wrapper itself)
calls a raw downloader. AGENT.md §1 — disk writes go through the wrapper.

This test greps the source tree for forbidden patterns and fails on hits.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent  # broll/
WRAPPER_PATH = ROOT / "lib" / "asset_wrapper.py"

# Patterns that indicate a network call bypassing the wrapper.
# urllib.request appears legitimately in asset_wrapper (the wrapper IS the path)
# and in source clients for SEARCH (read-only, no disk write) — those still need
# to call asset_wrapper.download() for the actual file. So we look specifically
# for byte-saving patterns that bypass the wrapper.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("urllib.urlretrieve",     re.compile(r"\burllib\.(?:request\.)?urlretrieve\b")),
    ("requests.get().content", re.compile(r"requests\.(?:get|post)\s*\([^)]*\)\.content")),
    ("requests stream save",   re.compile(r"requests\.(?:get|post)\s*\([^)]*stream\s*=\s*True")),
    ("open(...,'wb')+urlopen", re.compile(r"open\([^)]+['\"]wb['\"]\s*\).*urlopen", re.DOTALL)),
]

# Files explicitly allowed to contain disk-write primitives.
ALLOWLIST = {
    WRAPPER_PATH.resolve(),
    (ROOT / "tests" / "test_no_raw_downloads.py").resolve(),  # this file mentions patterns
    (ROOT / "tests" / "test_asset_wrapper.py").resolve(),     # test fixture writes
}


def _python_files() -> list[Path]:
    return [
        p for p in ROOT.rglob("*.py")
        if p.resolve() not in ALLOWLIST
        and "__pycache__" not in p.parts
    ]


@pytest.mark.parametrize("py_file", _python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_raw_download_patterns(py_file: Path) -> None:
    text = py_file.read_text(encoding="utf-8")
    hits = [(name, pat.findall(text)) for name, pat in FORBIDDEN_PATTERNS]
    offenders = [(name, matches) for name, matches in hits if matches]
    assert not offenders, (
        f"{py_file.relative_to(ROOT)} contains forbidden raw-download pattern(s): "
        f"{offenders}. Route through broll.lib.asset_wrapper instead."
    )

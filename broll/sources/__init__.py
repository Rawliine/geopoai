"""Stock + AI source clients.

A source module exposes:
    search(query: str, limit: int) -> list[SearchResult]   # stock only
    fetch(result: SearchResult, target_path, *, shot_id) -> dict  # stock only
    generate(prompt: str, seed: int, params: dict, *, shot_id, target_path) -> dict  # AI only

All disk writes must go through broll.lib.asset_wrapper. The SOURCES registry
is used by broll/lib/cascade.py (Phase 1). Phase 0 ships only the Pexels client.
"""

from . import pexels

SOURCES = {
    "pexels": pexels,
}

"""Stock + AI source clients.

Public surface
--------------
* ``SOURCES``: name → module mapping for the cascade walker.
* ``CASCADE_ORDER``: stable ordering used by ``broll.lib.cascade``. The order
  is from recap(1).md §2 — Wikimedia/LoC/NARA/Archive favour archival and
  named content; Pexels/Pixabay are last because they're generic-modern.
* ``SearchResult``: re-exported normalized candidate type.

Each source module exposes:
    NAME = "<name>"
    def search(query, limit, *, orientation=None) -> list[SearchResult]
    def fetch(result, target_path, *, shot_id, verification=None) -> dict
"""

from . import archive_org, loc, ltx_video, nara, pexels, pixabay, wan_video, wikimedia
from ._base import SearchResult

# Stock sources — used by the cascade walker.
SOURCES = {
    "wikimedia":   wikimedia,
    "loc":         loc,
    "nara":        nara,
    "archive_org": archive_org,
    "pexels":      pexels,
    "pixabay":     pixabay,
}

# AI sources — invoked directly by the pipeline via ai_router. Not part of
# the cascade. Keys match the strings returned by ``broll.lib.ai_router``.
AI_SOURCES = {
    "ltx-2.3":  ltx_video,
    "wan-2.2":  wan_video,
}

CASCADE_ORDER = ("wikimedia", "loc", "nara", "archive_org", "pexels", "pixabay")

__all__ = ["SOURCES", "AI_SOURCES", "CASCADE_ORDER", "SearchResult"]

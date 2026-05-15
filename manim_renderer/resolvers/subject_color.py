"""Subject color inheritance resolver (Phase 2 / PR M).

When a callout points at a subject and the author doesn't pass an
explicit `color`, derive the accent from the subject's own palette
position. Rules:

  * `subject = "<host>:cell:i,j"` and host is a PayoffMatrix:
      → row player's actor color if the row's payoff dominates,
      → col player's actor color if the col's payoff dominates,
      → highlight (semantic) on a tie.
  * `subject = "<host>:row:i"` and host is a PayoffMatrix:
      → row player's actor color.
  * `subject = "<host>:col:j"` and host is a PayoffMatrix:
      → col player's actor color.
  * Bare `subject = "<id>"` where the host has a palette `color` attr
    (StatBlock, BarChart series, etc.):
      → the host's color.
  * Anything else (no host, no resolvable refinement, or no inferable
    palette key): `highlight` fallback.

Explicit `params.color` always wins — the runner does NOT call this
helper when the author set `color`.

The output is a palette key (not a hex string), so the CalloutBox's
existing `_resolve_accent_hex` can convert it the same way it converts
an explicit `params.color`. Keeping it palette-keyed preserves the
"colors are pulled from theme/palette.py, never hardcoded" rule.
"""

from __future__ import annotations

from typing import Optional

from manim_renderer.resolvers.subject_placement import parse_subject


_FALLBACK_KEY = "highlight"


def inherit_subject_color(subject: str, id_to_mobject: dict) -> str:
    """Return the palette key a callout should adopt from `subject`."""
    host_id, parts = parse_subject(subject)
    host = id_to_mobject.get(host_id)
    if host is None:
        return _FALLBACK_KEY

    # PayoffMatrix-shaped subjects: duck-type per AGENT.md rule 14.
    if parts and _looks_like_payoff_matrix(host):
        return _payoff_matrix_color(host, parts)

    # Bare subject: try the host's own color attr.
    return _host_color(host)


def _looks_like_payoff_matrix(host) -> bool:
    return (
        hasattr(host, "row_player_color")
        and hasattr(host, "col_player_color")
        and hasattr(host, "n_rows")
        and hasattr(host, "n_cols")
    )


def _payoff_matrix_color(host, parts: list[str]) -> str:
    """Walk a payoff-matrix refinement to a palette key.

    `parts` examples:
        ["cell", "1,0"]  -> row vs col dominance
        ["row", "0"]     -> row actor
        ["col", "1"]     -> col actor
    """
    if len(parts) < 1:
        return _FALLBACK_KEY
    kind = parts[0]

    if kind == "row":
        return _palette_key_from_hex(host.row_player_color())
    if kind == "col":
        return _palette_key_from_hex(host.col_player_color())
    if kind == "cell" and len(parts) >= 2:
        try:
            i_str, j_str = parts[1].split(",")
            i, j = int(i_str), int(j_str)
        except (ValueError, TypeError):
            return _FALLBACK_KEY
        # Dominance: read the (a, b) payoffs at (i, j). The host stores
        # cells as a nested list of dicts. We use duck-type access.
        cells = getattr(host, "params", {}).get("cells")
        if not cells:
            return _FALLBACK_KEY
        try:
            cell = cells[i][j]
        except (IndexError, TypeError, KeyError):
            return _FALLBACK_KEY
        a = float(cell.get("a", 0.0))
        b = float(cell.get("b", 0.0))
        if a > b:
            return _palette_key_from_hex(host.row_player_color())
        if b > a:
            return _palette_key_from_hex(host.col_player_color())
        return _FALLBACK_KEY  # tie

    return _FALLBACK_KEY


def _host_color(host) -> str:
    """Inspect a non-matrix host for a palette key.

    StatBlock, BarChart, MetricGroup expose their accent color through
    `params.color`. Falling back to that string is the simplest correct
    behavior; the runner will validate it against the palette downstream.
    """
    params = getattr(host, "params", None) or {}
    color = params.get("color")
    if color:
        return color
    return _FALLBACK_KEY


def _palette_key_from_hex(hex_value: str) -> str:
    """Reverse-lookup a hex string into a palette key.

    PayoffMatrix stores actor colors as resolved hex values (not keys),
    so we reverse the map. Falls back to `highlight` on miss.
    """
    from manim_renderer.theme.palette import ACTORS, SEMANTIC, UI

    palette = {**ACTORS, **SEMANTIC, **UI}
    for key, hex_ in palette.items():
        if hex_.lower() == str(hex_value).lower():
            return key
    return _FALLBACK_KEY

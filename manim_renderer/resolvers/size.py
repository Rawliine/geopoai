"""Size resolver — turn a (role, format, kind) triple into Manim unit dims.

Manim frame is 14.2 x 8.0 in horizontal, 8.0 x 14.2 in vertical (origin at center).
Components never hardcode unit values — they call `resolve_size(role, format, kind)`.

Adding a new `kind` is one table edit. Adding a new role would touch the schema enum
and every kind row.
"""

from __future__ import annotations

# (width_units, height_units) per (kind -> role) per format.
# Numbers tuned to leave breathing room around the slot in each layout.
SIZE_TABLE: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
    "horizontal": {
        "default": {
            "small":  (4.0, 2.5),
            "medium": (6.0, 4.0),
            "large":  (10.0, 6.0),
        },
        "matrix": {
            "small":  (4.0, 4.0),
            "medium": (5.5, 5.5),
            "large":  (7.0, 7.0),
        },
        "chart": {
            "small":  (5.0, 3.0),
            "medium": (7.0, 4.0),
            "large":  (10.0, 5.5),
        },
        "tree": {
            "small":  (5.0, 3.0),
            "medium": (8.0, 5.0),
            "large":  (12.0, 7.0),
        },
        "web": {
            "small":  (4.5, 4.5),
            "medium": (6.5, 6.0),
            "large":  (9.0, 7.0),
        },
    },
    "vertical": {
        "default": {
            "small":  (3.5, 4.5),
            "medium": (5.5, 7.0),
            "large":  (7.0, 11.0),
        },
        "matrix": {
            "small":  (4.0, 4.0),
            "medium": (5.5, 5.5),
            "large":  (7.0, 7.0),
        },
        "chart": {
            "small":  (4.5, 3.5),
            "medium": (6.5, 5.0),
            "large":  (7.5, 7.0),
        },
        "tree": {
            "small":  (5.0, 5.0),
            "medium": (6.5, 8.0),
            "large":  (7.5, 11.0),
        },
        "web": {
            "small":  (4.5, 4.5),
            "medium": (6.0, 6.0),
            "large":  (7.5, 9.0),
        },
    },
}

SIZE_ROLES: tuple[str, ...] = ("small", "medium", "large")
SIZE_KINDS: tuple[str, ...] = tuple(SIZE_TABLE["horizontal"].keys())


def resolve_size(
    role: str,
    format: str,
    kind: str = "default",
) -> tuple[float, float]:
    """Return `(width, height)` in Manim units.

    Args:
        role: one of `SIZE_ROLES` (`"small" | "medium" | "large"`).
        format: `"horizontal"` or `"vertical"`.
        kind: component family (`"default" | "matrix" | "chart" | "tree" | "web"`).

    Raises:
        KeyError: on unknown format/kind/role, with the available options listed.
    """
    fmt_table = SIZE_TABLE.get(format)
    if fmt_table is None:
        raise KeyError(
            f"unknown format {format!r}; available: {sorted(SIZE_TABLE)}"
        )
    kind_table = fmt_table.get(kind)
    if kind_table is None:
        raise KeyError(
            f"unknown kind {kind!r} (format={format!r}); "
            f"available: {sorted(fmt_table)}"
        )
    dims = kind_table.get(role)
    if dims is None:
        raise KeyError(
            f"unknown role {role!r} (format={format!r}, kind={kind!r}); "
            f"available: {sorted(kind_table)}"
        )
    return dims

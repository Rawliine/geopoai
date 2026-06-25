"""Typed errors for map version resolution (W14)."""


class MapVersionNotFoundError(Exception):
    """Raised when a map version cannot be resolved; carries nearest alternatives."""

    def __init__(self, version: str, suggestions: list[str]) -> None:
        self.version = version
        self.suggestions = list(suggestions)
        hint = ", ".join(suggestions) if suggestions else "(none)"
        super().__init__(
            f"Map version '{version}' not found. Nearest available: {hint}"
        )

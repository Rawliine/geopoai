"""Typed errors for the B-roll layer. Importable from any submodule."""


class BrollError(Exception):
    """Base class for all B-roll errors."""


class SchemaValidationError(BrollError):
    """A shot spec or asset meta failed JSON Schema validation."""


class AssetWrapperError(BrollError):
    """The wrapper failed to materialize an asset + meta pair atomically."""


class SourceError(BrollError):
    """A source client failed (network, auth, parse). Recoverable via cascade fallthrough."""


class SourceAuthError(SourceError):
    """The source requires credentials we don't have."""


class NoCandidatesError(BrollError):
    """The cascade walked all sources and produced nothing usable."""


class VerificationError(BrollError):
    """Verification subsystem rejected all candidates."""

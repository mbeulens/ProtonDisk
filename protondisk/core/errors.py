"""Exception hierarchy for ProtonDisk core."""


class ProtonDiskError(Exception):
    """Base class for all ProtonDisk errors."""


class CLINotFoundError(ProtonDiskError):
    """The proton-drive binary could not be located."""


class AuthError(ProtonDiskError):
    """Not logged in, or the session has expired."""


class NotFoundError(ProtonDiskError):
    """A requested path does not exist."""


class ConflictError(ProtonDiskError):
    """A name collision or upload conflict occurred."""


class RateLimitError(ProtonDiskError):
    """Proton fair-use throttling was triggered."""

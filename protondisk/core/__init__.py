"""ProtonDisk core: typed wrapper around the official proton-drive CLI."""
from .client import ProtonDisk
from .models import Entry, AuthStatus, TransferResult, ShareInfo
from .errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
)

__all__ = [
    "ProtonDisk", "Entry", "AuthStatus", "TransferResult", "ShareInfo",
    "ProtonDiskError", "CLINotFoundError", "AuthError",
    "NotFoundError", "ConflictError", "RateLimitError",
]

import pytest

from protondisk.core.errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
)


@pytest.mark.parametrize(
    "subclass",
    [CLINotFoundError, AuthError, NotFoundError, ConflictError, RateLimitError],
)
def test_all_errors_derive_from_base(subclass):
    err = subclass("boom")
    assert isinstance(err, ProtonDiskError)
    assert str(err) == "boom"

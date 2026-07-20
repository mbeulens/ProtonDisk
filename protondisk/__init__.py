"""ProtonDisk — Proton Drive as a mounted disk and graphical browser."""
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path


def _read_version() -> str:
    # VERSION is this project's single source of truth and changes every commit,
    # so prefer it. In a source checkout (incl. editable installs) it sits next
    # to the package; installed metadata would be frozen/stale. Fall back to
    # installed metadata for a real wheel where no VERSION file ships alongside.
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    try:
        return _pkg_version("protondisk")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _read_version()
__all__ = ["__version__"]

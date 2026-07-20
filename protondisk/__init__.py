"""ProtonDisk — Proton Drive as a mounted disk and graphical browser."""
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path


def _read_version() -> str:
    try:
        return _pkg_version("protondisk")
    except PackageNotFoundError:
        pass
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


__version__ = _read_version()
__all__ = ["__version__"]

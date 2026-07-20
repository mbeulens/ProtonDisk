"""ProtonDisk — Proton Drive as a mounted disk and graphical browser."""
from pathlib import Path

_version_file = Path(__file__).resolve().parent.parent / "VERSION"
try:
    __version__ = _version_file.read_text(encoding="utf-8").strip()
except OSError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]

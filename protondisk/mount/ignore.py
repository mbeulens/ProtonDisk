"""Which filenames are ephemeral editor/OS artifacts kept local-only.

Files whose basename matches one of these patterns are handled entirely in a local
scratch area by the mount and are NEVER uploaded to Proton Drive — so editors and
file managers can create their swap/lock/temp files without cluttering the Drive
or wasting uploads. Conservative: only true throwaway artifacts (backups like
``file~`` and generic ``*.tmp`` are intentionally NOT here — a user may want them).
"""
from __future__ import annotations

from fnmatch import fnmatch

_PATTERNS = (
    ".*.swp", ".*.swo", ".*.swn", ".*.swpx",  # vim swap files
    ".#*",                                     # emacs lock
    "#*#",                                     # emacs auto-save
    ".goutputstream-*",                        # GNOME / gio atomic-save temp
    ".~lock.*#",                               # LibreOffice lock
    "~$*",                                     # Microsoft Office temp
    ".DS_Store", "._*",                        # macOS
    "Thumbs.db", "desktop.ini",               # Windows
    "4913",                                    # vim writability probe
)


def is_ephemeral(name: str) -> bool:
    """True if `name` (a basename) is an editor/OS temp file to keep local-only."""
    return any(fnmatch(name, pattern) for pattern in _PATTERNS)

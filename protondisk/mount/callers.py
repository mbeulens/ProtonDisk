"""Recognise the desktop preview/indexing helpers whose reads we refuse.

Opening a folder in a file manager sets off a swarm of background helpers:
thumbnailers render previews, search indexers extract text. On a local disk that
is cheap. On a Proton Drive mount every one of those reads means downloading the
whole file over the network — so browsing a folder of photos or music would fetch
the entire folder, slowly, and announce each fetch.

The mount therefore refuses reads coming from those helpers (EACCES). The file
manager falls back to a generic file-type icon and nothing is downloaded. Reads
from the file manager itself and from ordinary applications are untouched, so
opening, copying and editing files all behave exactly as before.
"""
from __future__ import annotations

import os
from fnmatch import fnmatch

# Matched against the process name (argv[0]'s basename, else the kernel comm).
_PREVIEW_PROCESSES = (
    "*thumbnail*",                           # gdk-pixbuf/totem/evince/… thumbnailers
    "tumbler*",                              # XFCE thumbnail daemon
    "tracker-extract*", "tracker-miner*",    # GNOME search index (tracker 3)
    "localsearch*", "tinysparql*",           # tracker's successors
    "baloo_file*",                           # KDE search index
    "gsf-office-*",                          # office-document thumbnailer
)

# GNOME runs thumbnailers inside a bwrap sandbox, so the reader is usually the
# helper itself — but look at a couple of parents too, in case a wrapper process
# is the one holding the file open.
_ANCESTORS = 3


def _proc_name(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv0 = f.read().split(b"\0", 1)[0].decode(errors="replace")
        if argv0:
            return os.path.basename(argv0)
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()      # truncated to 15 chars, still matchable
    except OSError:
        return None


def _parent_pid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


def is_preview_name(name: str | None) -> bool:
    """True if `name` (a process basename) is a thumbnailer or search indexer."""
    if not name:
        return False
    return any(fnmatch(name, pattern) for pattern in _PREVIEW_PROCESSES)


def is_preview_process(pid: int, *, name_of=_proc_name, parent_of=_parent_pid) -> bool:
    """True if `pid` — or a near ancestor — is preview/indexing machinery."""
    for _ in range(_ANCESTORS + 1):
        if pid <= 1:
            return False
        if is_preview_name(name_of(pid)):
            return True
        pid = parent_of(pid)
    return False

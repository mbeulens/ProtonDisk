"""Mount lifecycle: set up the FUSE mount and tear it down."""
from __future__ import annotations

import os
import shutil
import subprocess

from fuse import FUSE

from .fs import ProtonDiskFS
from .notify import Notifier


def default_mountpoint() -> str:
    return os.path.expanduser("~/ProtonDisk")


def mount(disk, mountpoint: str, *, ttl: float = 5.0, foreground: bool = True) -> None:
    os.makedirs(mountpoint, exist_ok=True)
    fs = ProtonDiskFS(disk, ttl=ttl, notifier=Notifier())
    FUSE(fs, mountpoint, foreground=foreground, nothreads=True)


def unmount(mountpoint: str) -> bool:
    for tool in ("fusermount3", "fusermount"):
        if shutil.which(tool):
            return subprocess.run([tool, "-u", mountpoint]).returncode == 0
    return False

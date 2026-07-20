"""Mount lifecycle: set up the FUSE mount and tear it down."""
from __future__ import annotations

import os
import shutil
import subprocess

from fuse import FUSE

from .fs import ProtonDiskFS


def default_mountpoint() -> str:
    return os.path.expanduser("~/ProtonDisk")


def mount(disk, mountpoint: str, *, ttl: float = 5.0, foreground: bool = True) -> None:
    os.makedirs(mountpoint, exist_ok=True)
    FUSE(ProtonDiskFS(disk, ttl=ttl), mountpoint,
         foreground=foreground, ro=True, nothreads=True)


def unmount(mountpoint: str) -> bool:
    for tool in ("fusermount3", "fusermount"):
        if shutil.which(tool):
            return subprocess.run([tool, "-u", mountpoint]).returncode == 0
    return False

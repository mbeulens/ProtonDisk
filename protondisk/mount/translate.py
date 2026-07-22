"""Pure helpers mapping between FUSE paths/attrs and Proton Drive (no fuse import)."""
from __future__ import annotations

import os
import stat as stat_mod

ROOT = "/my-files"


def proton_path(fuse_path: str) -> str:
    rel = fuse_path.strip("/")
    return ROOT if not rel else f"{ROOT}/{rel}"


def is_write_flags(flags: int) -> bool:
    if (flags & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR):
        return True
    return bool(flags & (os.O_APPEND | os.O_CREAT | os.O_TRUNC))


def stat_dict(entry, now: float) -> dict:
    # The mount is read-write, so advertise writable modes — file managers
    # (Nautilus) check these bits and refuse paste/save/delete on a 0o555/0o444
    # directory even when the underlying FUSE fs would allow the operation.
    mtime = entry.mtime if entry.mtime is not None else now
    if entry.is_dir:
        mode, nlink, size = stat_mod.S_IFDIR | 0o755, 2, 0
    else:
        mode, nlink, size = stat_mod.S_IFREG | 0o644, 1, (entry.size or 0)
    return {
        "st_mode": mode, "st_nlink": nlink, "st_size": size,
        "st_mtime": mtime, "st_ctime": mtime, "st_atime": mtime,
        "st_uid": os.getuid(), "st_gid": os.getgid(),
    }


def root_stat_dict(now: float) -> dict:
    return {
        "st_mode": stat_mod.S_IFDIR | 0o755, "st_nlink": 2, "st_size": 0,
        "st_mtime": now, "st_ctime": now, "st_atime": now,
        "st_uid": os.getuid(), "st_gid": os.getgid(),
    }

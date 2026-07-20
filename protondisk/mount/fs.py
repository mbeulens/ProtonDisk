"""Read-only FUSE operations over the ProtonDisk core (fusepy)."""
from __future__ import annotations

import errno
import os
import shutil
import tempfile
import time

from fuse import FuseOSError, Operations

from protondisk.core.errors import ProtonDiskError
from .cache import ListingCache
from .translate import proton_path, is_write_flags, stat_dict, root_stat_dict


class ProtonDiskFS(Operations):
    def __init__(self, disk, ttl: float = 5.0) -> None:
        self._disk = disk
        self._cache = ListingCache(ttl=ttl)
        self._open_files: dict[int, tuple] = {}
        self._next_fh = 1

    # ---- internals ----
    def _listing(self, proton_dir: str):
        cached = self._cache.get(proton_dir)
        if cached is None:
            cached = self._disk.list(proton_dir)
            self._cache.put(proton_dir, cached)
        return cached

    def _find_entry(self, fuse_path: str):
        parent_fuse, _, name = fuse_path.rstrip("/").rpartition("/")
        for entry in self._listing(proton_path(parent_fuse or "/")):
            if entry.name == name:
                return entry
        return None

    # ---- read ops ----
    def getattr(self, path, fh=None):
        if path == "/":
            return root_stat_dict(time.time())
        entry = self._find_entry(path)
        if entry is None:
            raise FuseOSError(errno.ENOENT)
        return stat_dict(entry, time.time())

    def readdir(self, path, fh):
        entries = self._listing(proton_path(path))
        return [".", "..", *[e.name for e in entries]]

    def statfs(self, path):
        return {"f_bsize": 4096, "f_frsize": 4096, "f_blocks": 0, "f_bfree": 0,
                "f_bavail": 0, "f_files": 0, "f_ffree": 0, "f_namemax": 255}

    # ---- download-on-open ----
    def open(self, path, flags):
        if is_write_flags(flags):
            raise FuseOSError(errno.EROFS)
        entry = self._find_entry(path)
        if entry is None:
            raise FuseOSError(errno.ENOENT)
        if entry.is_dir:
            raise FuseOSError(errno.EISDIR)
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        try:
            self._disk.download(proton_path(path), tmpdir)
        except ProtonDiskError:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise FuseOSError(errno.EIO)
        local = os.path.join(tmpdir, os.path.basename(path))
        fobj = open(local, "rb")
        fh = self._next_fh
        self._next_fh += 1
        self._open_files[fh] = (tmpdir, fobj)
        return fh

    def read(self, path, size, offset, fh):
        _tmpdir, fobj = self._open_files[fh]
        fobj.seek(offset)
        return fobj.read(size)

    def release(self, path, fh):
        entry = self._open_files.pop(fh, None)
        if entry is not None:
            tmpdir, fobj = entry
            fobj.close()
            shutil.rmtree(tmpdir, ignore_errors=True)
        return 0

    # ---- read-only enforcement ----
    def _readonly(self, *args, **kwargs):
        raise FuseOSError(errno.EROFS)

    write = create = mkdir = unlink = rmdir = _readonly
    rename = truncate = chmod = chown = symlink = link = _readonly

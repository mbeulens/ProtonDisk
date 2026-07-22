"""Read-only FUSE operations over the ProtonDisk core (fusepy)."""
from __future__ import annotations

import errno
import os
import shutil
import stat as stat_mod
import tempfile
import time

from fuse import FuseOSError, Operations

from protondisk.core.errors import ProtonDiskError
from .cache import ListingCache
from .notify import Notifier
from .translate import proton_path, is_write_flags, stat_dict, root_stat_dict


class _Handle:
    __slots__ = ("tmpdir", "fobj", "path", "writable", "dirty")

    def __init__(self, tmpdir, fobj, path, writable):
        self.tmpdir = tmpdir
        self.fobj = fobj
        self.path = path
        self.writable = writable
        self.dirty = False

    def local(self):
        return os.path.join(self.tmpdir, os.path.basename(self.path))


class ProtonDiskFS(Operations):
    def __init__(self, disk, ttl: float = 5.0, notifier=None) -> None:
        self._disk = disk
        self._cache = ListingCache(ttl=ttl)
        self._notifier = notifier or Notifier(enabled=False)
        self._open_files: dict[int, _Handle] = {}
        self._write_handles: dict[str, _Handle] = {}
        self._next_fh = 1

    # ---- internals ----
    def _listing(self, proton_dir: str):
        cached = self._cache.get(proton_dir)
        if cached is None:
            try:
                cached = self._disk.list(proton_dir)
            except ProtonDiskError:
                raise FuseOSError(errno.EIO)  # a Drive/network error, not "bad argument"
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
        h = self._write_handles.get(path)
        if h is not None:
            h.fobj.flush()
            info = os.stat(h.local())
            now = time.time()
            return {
                "st_mode": stat_mod.S_IFREG | 0o644, "st_nlink": 1,
                "st_size": info.st_size, "st_mtime": info.st_mtime,
                "st_ctime": info.st_mtime, "st_atime": now,
                "st_uid": os.getuid(), "st_gid": os.getgid(),
            }
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

    # ---- handle registry ----
    def _register(self, tmpdir, fobj, path, writable, dirty=False) -> int:
        h = _Handle(tmpdir, fobj, path, writable)
        h.dirty = dirty
        fh = self._next_fh
        self._next_fh += 1
        self._open_files[fh] = h
        if writable:
            self._write_handles[path] = h
        return fh

    # ---- open / read / write / truncate ----
    def open(self, path, flags):
        writable = is_write_flags(flags)
        entry = self._find_entry(path)
        name = os.path.basename(path)
        if not writable:
            if entry is None:
                raise FuseOSError(errno.ENOENT)
            if entry.is_dir:
                raise FuseOSError(errno.EISDIR)
            tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
            note = self._notifier.begin(f"Opening {name}…")
            try:
                self._disk.download(
                    proton_path(path), tmpdir,
                    progress=lambda ph: self._notifier.update(note, f"{ph} {name}"))
                fobj = open(os.path.join(tmpdir, name), "rb")
            except (ProtonDiskError, OSError):
                self._notifier.finish(note, f"Failed: {name}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise FuseOSError(errno.EIO)
            self._notifier.finish(note, f"Ready: {name}")
            return self._register(tmpdir, fobj, path, writable=False)
        # write intent
        if entry is not None and entry.is_dir:
            raise FuseOSError(errno.EISDIR)
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        local = os.path.join(tmpdir, name)
        try:
            if entry is not None and not (flags & os.O_TRUNC):
                self._disk.download(proton_path(path), tmpdir)  # keep existing bytes
                fobj = open(local, "r+b")
                # opened for edit; only re-upload if something is actually written
                start_dirty = False
            else:
                fobj = open(local, "w+b")
                # a brand-new file, or O_TRUNC emptying an existing one: the empty
                # (or about-to-be-rewritten) buffer IS the intended new content, so
                # it must be uploaded even if the app never calls write().
                start_dirty = True
        except (ProtonDiskError, OSError):
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise FuseOSError(errno.EIO)
        return self._register(tmpdir, fobj, path, writable=True, dirty=start_dirty)

    def create(self, path, mode, fi=None):
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        fobj = open(os.path.join(tmpdir, os.path.basename(path)), "w+b")
        # a freshly created file must be persisted even if nothing is written to it
        # (touch, cp of an empty file, saving a 0-byte document).
        return self._register(tmpdir, fobj, path, writable=True, dirty=True)

    def read(self, path, size, offset, fh):
        h = self._open_files[fh]
        h.fobj.seek(offset)
        return h.fobj.read(size)

    def write(self, path, data, offset, fh):
        h = self._open_files[fh]
        h.fobj.seek(offset)
        h.fobj.write(data)
        h.dirty = True
        return len(data)

    def truncate(self, path, length, fh=None):
        if fh is not None and fh in self._open_files:
            h = self._open_files[fh]
            h.fobj.truncate(length)
            h.dirty = True
            return 0
        # standalone truncate (no open handle): download, truncate, upload-replace
        entry = self._find_entry(path)
        if entry is None:
            raise FuseOSError(errno.ENOENT)
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        try:
            self._disk.download(proton_path(path), tmpdir)
            local = os.path.join(tmpdir, os.path.basename(path))
            with open(local, "r+b") as f:
                f.truncate(length)
            parent = proton_path(os.path.dirname(path) or "/")
            self._disk.upload(local, parent, conflict="replace")
            self._cache.invalidate(parent)
        except (ProtonDiskError, OSError):
            raise FuseOSError(errno.EIO)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return 0

    # ---- flush / release / upload ----
    def _upload_handle(self, h) -> None:
        if not (h.writable and h.dirty):
            return
        h.fobj.flush()
        os.fsync(h.fobj.fileno())
        name = os.path.basename(h.path)
        parent = proton_path(os.path.dirname(h.path) or "/")
        note = self._notifier.begin(f"Saving {name}…")
        try:
            self._disk.upload(
                h.local(), parent, conflict="replace",
                progress=lambda ph: self._notifier.update(note, f"{ph} {name}"))
        except (ProtonDiskError, OSError):
            self._notifier.finish(note, f"Upload failed: {name}")
            raise FuseOSError(errno.EIO)
        self._notifier.finish(note, f"Saved {name} to Proton Drive")
        h.dirty = False
        self._cache.invalidate(parent)

    def flush(self, path, fh):
        h = self._open_files.get(fh)
        if h is not None:
            self._upload_handle(h)
        return 0

    def fsync(self, path, datasync, fh):
        return self.flush(path, fh)

    def release(self, path, fh):
        h = self._open_files.pop(fh, None)
        if h is None:
            return 0
        try:
            if h.writable and h.dirty:
                try:
                    self._upload_handle(h)
                except FuseOSError:
                    pass  # already surfaced at flush for well-behaved apps; don't leak
        finally:
            h.fobj.close()
            shutil.rmtree(h.tmpdir, ignore_errors=True)
            if self._write_handles.get(h.path) is h:
                del self._write_handles[h.path]
        return 0

    # ---- read-only enforcement ----
    def _readonly(self, *args, **kwargs):
        raise FuseOSError(errno.EROFS)

    chmod = chown = symlink = link = _readonly

    # ---- namespace ops ----
    def _entry_names(self, fuse_dir):
        return {e.name for e in self._listing(proton_path(fuse_dir))}

    def mkdir(self, path, mode):
        try:
            self._disk.mkdir(proton_path(path))
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(os.path.dirname(path) or "/"))
        return 0

    def unlink(self, path):
        try:
            self._disk.trash(proton_path(path))
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(os.path.dirname(path) or "/"))
        return 0

    rmdir = unlink

    def rename(self, old, new):
        if old == new:
            return 0  # renaming a path onto itself is a no-op, not a conflict
        old_parent = os.path.dirname(old) or "/"
        new_parent = os.path.dirname(new) or "/"
        old_name = os.path.basename(old)
        new_name = os.path.basename(new)
        target_names = self._entry_names(new_parent)
        if new_name in target_names:
            raise FuseOSError(errno.EEXIST)  # Proton won't overwrite
        # a cross-parent move lands old_name in the target dir first; block that
        # collision too, before mutating anything.
        if old_parent != new_parent and old_name != new_name and old_name in target_names:
            raise FuseOSError(errno.EEXIST)
        try:
            if old_parent == new_parent:
                self._disk.rename(proton_path(old), new_name)
            else:
                self._disk.move(proton_path(old), proton_path(new_parent))
                if new_name != old_name:
                    moved = f"{proton_path(new_parent)}/{old_name}"
                    self._disk.rename(moved, new_name)
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(old_parent))
        self._cache.invalidate(proton_path(new_parent))
        return 0

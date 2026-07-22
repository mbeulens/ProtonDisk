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
from .ignore import is_ephemeral
from .notify import Notifier
from .translate import proton_path, is_write_flags, stat_dict, root_stat_dict

# When a rename replaces an existing name we trash it first; the rename onto the
# freed name may briefly still collide (Proton is eventually consistent), so retry.
_RENAME_RETRIES = 4
_RENAME_RETRY_DELAY = 0.5  # seconds between attempts

# How long a deleted name stays "gone" to mask Proton's eventual consistency
# (observed ~6s; use a safe margin). Cleared early when the name is recreated.
_TOMBSTONE_TTL = 30  # seconds


class _Handle:
    __slots__ = ("tmpdir", "fobj", "path", "writable", "dirty", "ephemeral")

    def __init__(self, tmpdir, fobj, path, writable, ephemeral=False):
        self.tmpdir = tmpdir
        self.fobj = fobj
        self.path = path
        self.writable = writable
        self.dirty = False
        self.ephemeral = ephemeral  # local-only editor/OS temp; never uploaded

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
        # Proton is eventually consistent: a just-trashed name still shows up in
        # listings for a few seconds. Tombstone deleted paths so getattr/readdir/
        # O_EXCL-create treat them as gone during that window (fixes nano/vim swap
        # files, `rm x; touch x`, atomic-save temp reuse). Cleared on recreate.
        self._tombstones: dict[str, float] = {}  # fuse path -> monotonic expiry
        # Editor/OS temp files (vim swap, GNOME temps, .DS_Store, …) live only here
        # and never touch the Drive — see ignore.is_ephemeral.
        self._local_root = tempfile.mkdtemp(prefix="protondisk-eph-")

    # ---- local-only ephemeral files (editor/OS temp; never uploaded) ----
    @staticmethod
    def _is_ephemeral(path: str) -> bool:
        return is_ephemeral(os.path.basename(path))

    def _eph_local(self, fuse_path: str) -> str:
        return os.path.join(self._local_root, fuse_path.lstrip("/"))

    def _eph_getattr(self, path: str):
        local = self._eph_local(path)
        if not os.path.exists(local):
            raise FuseOSError(errno.ENOENT)
        info = os.stat(local)
        now = time.time()
        return {
            "st_mode": stat_mod.S_IFREG | 0o644, "st_nlink": 1,
            "st_size": info.st_size, "st_mtime": info.st_mtime,
            "st_ctime": info.st_mtime, "st_atime": now,
            "st_uid": os.getuid(), "st_gid": os.getgid(),
        }

    def _eph_names(self, fuse_dir: str) -> list[str]:
        # ephemeral files created directly under this directory
        d = self._eph_local(fuse_dir if fuse_dir != "/" else "")
        try:
            return [n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))]
        except OSError:
            return []

    # ---- tombstones (mask a just-deleted name during eventual consistency) ----
    def _tombstone(self, path: str) -> None:
        self._tombstones[path] = time.monotonic() + _TOMBSTONE_TTL

    def _untombstone(self, path: str) -> None:
        self._tombstones.pop(path, None)

    def _is_tombstoned(self, path: str) -> bool:
        expiry = self._tombstones.get(path)
        if expiry is None:
            return False
        if time.monotonic() >= expiry:
            del self._tombstones[path]
            return False
        return True

    @staticmethod
    def _child(fuse_dir: str, name: str) -> str:
        return f"/{name}" if fuse_dir in ("", "/") else f"{fuse_dir.rstrip('/')}/{name}"

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
        if self._is_tombstoned(fuse_path):
            return None  # just deleted — treat as gone despite eventual consistency
        parent_fuse, _, name = fuse_path.rstrip("/").rpartition("/")
        for entry in self._listing(proton_path(parent_fuse or "/")):
            if entry.name == name:
                return entry
        return None

    # ---- read ops ----
    def getattr(self, path, fh=None):
        if path == "/":
            return root_stat_dict(time.time())
        if self._is_ephemeral(path):
            return self._eph_getattr(path)   # local-only; never touches the Drive
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
        names = [e.name for e in entries
                 if not self._is_tombstoned(self._child(path, e.name))
                 and not is_ephemeral(e.name)]      # ephemerals shown from local scratch
        names += self._eph_names(path)               # local-only temp files in this dir
        return [".", "..", *names]

    def statfs(self, path):
        return {"f_bsize": 4096, "f_frsize": 4096, "f_blocks": 0, "f_bfree": 0,
                "f_bavail": 0, "f_files": 0, "f_ffree": 0, "f_namemax": 255}

    # ---- handle registry ----
    def _register(self, tmpdir, fobj, path, writable, dirty=False, ephemeral=False) -> int:
        h = _Handle(tmpdir, fobj, path, writable, ephemeral=ephemeral)
        h.dirty = dirty
        fh = self._next_fh
        self._next_fh += 1
        self._open_files[fh] = h
        if writable and not ephemeral:
            self._write_handles[path] = h
        return fh

    # ---- open / read / write / truncate ----
    def _eph_open(self, path, flags):
        # open/create a local-only ephemeral file; never touches the Drive
        local = self._eph_local(path)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        writable = is_write_flags(flags)
        if not writable:
            if not os.path.exists(local):
                raise FuseOSError(errno.ENOENT)
            fobj = open(local, "rb")
        elif os.path.exists(local) and not (flags & os.O_TRUNC):
            fobj = open(local, "r+b")
        else:
            fobj = open(local, "w+b")
        eph_dir = os.path.dirname(local)
        return self._register(eph_dir, fobj, path, writable=writable, ephemeral=True)

    def open(self, path, flags):
        if self._is_ephemeral(path):
            return self._eph_open(path, flags)
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
        self._untombstone(path)  # opening for write (re)creates the name
        return self._register(tmpdir, fobj, path, writable=True, dirty=start_dirty)

    def create(self, path, mode, fi=None):
        if self._is_ephemeral(path):
            local = self._eph_local(path)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            fobj = open(local, "w+b")
            return self._register(os.path.dirname(local), fobj, path,
                                  writable=True, ephemeral=True)
        self._untombstone(path)  # recreating a just-deleted name is fine
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
        if self._is_ephemeral(path):
            local = self._eph_local(path)
            if not os.path.exists(local):
                raise FuseOSError(errno.ENOENT)
            with open(local, "r+b") as f:
                f.truncate(length)
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
        if h.ephemeral or not (h.writable and h.dirty):
            return  # ephemeral temp files are never uploaded
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
        if h.ephemeral:
            h.fobj.close()   # keep the local file (persists like a real file); no upload
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

    def chmod(self, path, mode):
        if self._is_ephemeral(path):
            return 0   # local-only temp; accept mode changes as a no-op
        raise FuseOSError(errno.EROFS)  # Proton Drive has no chmod

    chown = symlink = link = _readonly

    # ---- namespace ops ----
    def _entry_names(self, fuse_dir):
        return {e.name for e in self._listing(proton_path(fuse_dir))
                if not self._is_tombstoned(self._child(fuse_dir, e.name))}

    def mkdir(self, path, mode):
        try:
            self._disk.mkdir(proton_path(path))
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(os.path.dirname(path) or "/"))
        return 0

    def unlink(self, path):
        if self._is_ephemeral(path):
            local = self._eph_local(path)
            if not os.path.exists(local):
                raise FuseOSError(errno.ENOENT)
            os.remove(local)     # local-only; nothing to trash on the Drive
            return 0
        try:
            self._disk.trash(proton_path(path))
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(os.path.dirname(path) or "/"))
        self._tombstone(path)  # hide the ghost until Proton catches up
        return 0

    rmdir = unlink

    def rename(self, old, new):
        if old == new:
            return 0  # renaming a path onto itself is a no-op, not a conflict
        if self._is_ephemeral(old) or self._is_ephemeral(new):
            return self._rename_ephemeral(old, new)
        old_parent = os.path.dirname(old) or "/"
        new_parent = os.path.dirname(new) or "/"
        old_name = os.path.basename(old)
        new_name = os.path.basename(new)
        target_names = self._entry_names(new_parent)
        # A cross-parent move first lands old_name in the target dir; if that name
        # is taken by an unrelated file we can't safely resolve it.
        if old_parent != new_parent and old_name != new_name and old_name in target_names:
            raise FuseOSError(errno.EEXIST)
        overwrite = new_name in target_names
        try:
            if overwrite:
                # Proton has no atomic overwrite, so the classic "write temp then
                # rename over the original" save (GNOME Text Editor, VS Code) would
                # fail. Trash the destination first — recoverable via Proton trash —
                # then rename onto the freed name, retrying briefly to ride out the
                # window where the just-trashed name still reads as taken.
                self._disk.trash(f"{proton_path(new_parent)}/{new_name}")
            if old_parent == new_parent:
                self._rename_settling(
                    lambda: self._disk.rename(proton_path(old), new_name), overwrite)
            else:
                self._disk.move(proton_path(old), proton_path(new_parent))
                if new_name != old_name:
                    moved = f"{proton_path(new_parent)}/{old_name}"
                    self._rename_settling(
                        lambda: self._disk.rename(moved, new_name), overwrite)
        except ProtonDiskError:
            raise FuseOSError(errno.EIO)
        self._cache.invalidate(proton_path(old_parent))
        self._cache.invalidate(proton_path(new_parent))
        self._tombstone(old)      # the source name no longer exists...
        self._untombstone(new)    # ...and the destination now does
        return 0

    def _rename_ephemeral(self, old, new) -> int:
        src_eph, dst_eph = self._is_ephemeral(old), self._is_ephemeral(new)
        src_local = self._eph_local(old)
        if src_eph and dst_eph:
            # both local-only: a plain local move within the scratch area
            dst_local = self._eph_local(new)
            os.makedirs(os.path.dirname(dst_local), exist_ok=True)
            os.replace(src_local, dst_local)
            return 0
        if src_eph and not dst_eph:
            # atomic-save completion: a local temp is renamed onto a real Drive
            # file. Upload the temp's content to the destination (replace), then
            # drop the local temp. Nothing extra ever lands on the Drive.
            if not os.path.exists(src_local):
                raise FuseOSError(errno.ENOENT)
            new_parent = os.path.dirname(new) or "/"
            new_name = os.path.basename(new)
            staging = tempfile.mkdtemp(prefix="protondisk-mnt-")
            note = self._notifier.begin(f"Saving {new_name}…")
            try:
                shutil.copyfile(src_local, os.path.join(staging, new_name))
                self._disk.upload(
                    os.path.join(staging, new_name), proton_path(new_parent),
                    conflict="replace",
                    progress=lambda ph: self._notifier.update(note, f"{ph} {new_name}"))
            except (ProtonDiskError, OSError):
                self._notifier.finish(note, f"Save failed: {new_name}")
                raise FuseOSError(errno.EIO)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            self._notifier.finish(note, f"Saved {new_name} to Proton Drive")
            os.remove(src_local)
            self._cache.invalidate(proton_path(new_parent))
            self._untombstone(new)
            return 0
        # src real -> dst ephemeral (rare): move the real file's content into the
        # local scratch, then trash the real source.
        entry = self._find_entry(old)
        if entry is None:
            raise FuseOSError(errno.ENOENT)
        dst_local = self._eph_local(new)
        os.makedirs(os.path.dirname(dst_local), exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="protondisk-mnt-")
        try:
            self._disk.download(proton_path(old), tmp)
            shutil.move(os.path.join(tmp, os.path.basename(old)), dst_local)
            self._disk.trash(proton_path(old))
        except (ProtonDiskError, OSError):
            raise FuseOSError(errno.EIO)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._cache.invalidate(proton_path(os.path.dirname(old) or "/"))
        self._tombstone(old)
        return 0

    def _rename_settling(self, op, retry) -> None:
        # A rename onto a just-trashed name can momentarily still see it as taken
        # (Proton is eventually consistent). When replacing, retry a few times to
        # let the trash settle; otherwise run once.
        if not retry:
            op()
            return
        last = None
        for attempt in range(_RENAME_RETRIES):
            try:
                op()
                return
            except ProtonDiskError as exc:
                last = exc
                if attempt < _RENAME_RETRIES - 1:
                    time.sleep(_RENAME_RETRY_DELAY)
        raise last

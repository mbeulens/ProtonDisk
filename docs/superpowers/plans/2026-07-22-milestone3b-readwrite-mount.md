# ProtonDisk Milestone 3 (increment 2) — Read-write FUSE Mount + Progress Notifications

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ProtonDisk FUSE mount **read-write** (copy files in, save, new folder, delete, rename/move) and show transfer activity via **desktop notifications**.

**Architecture:** Extends `protondisk/mount/fs.py`. Writes buffer to a per-handle local temp file and upload (`core.upload(..., conflict="replace")`) on flush/release — the CLI only does whole-file uploads. A best-effort `Notifier` (libnotify) surfaces download/encrypt/upload phases, reusing the `--verbose` progress stream already wired into `core.upload/download`. `getattr` reports the live buffer size for a file with an open write handle. All Drive errors map to `EIO`.

**Tech Stack:** Python 3.12+, fusepy, libnotify via `gi` (best-effort), stdlib, `pytest`. Run under `.venv-gui`.

## Global Constraints

- **Environment:** run ALL tests with **`.venv-gui/bin/pytest`** (fusepy + gi installed there). libfuse2 + `/dev/fuse` present for live mount; libnotify + the freedesktop Notifications D-Bus service present.
- **Layering:** `protondisk/mount/*` imports only `fuse`, stdlib, `protondisk.core`, and (in `notify.py`, best-effort) `gi`. Only `mounter.py` may call `fusermount`. Never the `proton-drive` binary.
- **Safety model:** the Drive holds only disposable test data (user-confirmed), so live write testing is free; still build to production quality. Every `ProtonDiskError` from the core maps to `FuseOSError(errno.EIO)`. Uploads always use `conflict="replace"`.
- **Notifications:** fire ONLY for content transfers (download-on-open, upload-on-flush/release); never for `getattr`/`readdir`. One notification per transfer, updated in place. The `Notifier` degrades to a silent no-op if libnotify/D-Bus is unavailable — it must never break the mount. Tests use a `FakeNotifier`; NO test fires a real notification.
- **Versioning (project GIT rules):** `VERSION` is the single source of truth; each task commit runs `scripts/bump-patch.sh` and pushes to `dev`. **The bump script skips patch 13** — if its stderr prints the skip notice for a commit, that commit's message MUST be exactly `To be sure to be sure!` (Task 3 is expected to land on this: 0.4.13 → 0.4.14). Increment done → **"Bump minor" → 0.6.0**.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'` + the message MUST end with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **GENUINE verification:** actually run tests, paste REAL output, never fabricate. Do NOT run a blocking `protondisk mount` in a subagent — the controller live-verifies the real mount.

## File Structure

```
protondisk/mount/
├── notify.py   # NEW: best-effort libnotify Notifier
├── fs.py       # MODIFY: read notification; write lifecycle; namespace ops
└── mounter.py  # MODIFY: mount read-write (drop ro=True); pass a Notifier
protondisk/cli.py  # MODIFY: mount help/message wording (read-write)
tests/mount/
├── test_notify.py         # NEW
├── test_fs_write.py       # NEW
├── test_fs_namespace.py   # NEW
└── (existing read tests unchanged)
```

---

### Task 1: `notify.py` — best-effort libnotify Notifier

**Files:** Create `protondisk/mount/notify.py`, `tests/mount/test_notify.py`.

**Interfaces:**
- `Notifier(app_name="ProtonDisk", enabled=True)`: when `enabled` is True, try `import gi; gi.require_version("Notify","0.7"); from gi.repository import Notify; Notify.init(app_name)` — on ANY exception, `self._enabled = False`. When `enabled=False`, stay disabled without importing gi (deterministic for tests).
- `enabled -> bool` property.
- `begin(body="") -> handle|None`: show a notification titled `"ProtonDisk"` with `body`; return the handle (or None when disabled/failed).
- `update(handle, body)`: update the same notification's body in place (no-op if handle None).
- `finish(handle, body, timeout_ms=3000)`: final update with a short timeout (no-op if handle None).
- All methods swallow libnotify exceptions (never raise into the FUSE loop).

- [ ] **Step 1: Write the failing test** — `tests/mount/test_notify.py`:
```python
from protondisk.mount.notify import Notifier


def test_disabled_notifier_is_silent_noop():
    n = Notifier(enabled=False)              # deterministic: never touches gi/D-Bus
    assert n.enabled is False
    assert n.begin("hi") is None             # returns None when disabled
    n.update(None, "x")                      # no raise
    n.finish(None, "done")                   # no raise


def test_methods_tolerate_none_handle():
    n = Notifier(enabled=False)
    # even if a caller passes None (e.g. begin failed), update/finish must not raise
    n.update(None, "phase")
    n.finish(None, "done", timeout_ms=1000)


def test_enabled_flag_exposed():
    assert hasattr(Notifier(enabled=False), "enabled")
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: protondisk.mount.notify`). Run: `.venv-gui/bin/pytest tests/mount/test_notify.py -v`

- [ ] **Step 3: Implement** — `protondisk/mount/notify.py`:
```python
"""Best-effort desktop notifications via libnotify.

Degrades to a silent no-op if libnotify / the notification D-Bus service is not
available, so the mount never breaks (headless, cron, minimal desktops).
"""
from __future__ import annotations

SUMMARY = "ProtonDisk"
_ICON = "folder-remote"


class Notifier:
    def __init__(self, app_name: str = "ProtonDisk", enabled: bool = True) -> None:
        self._enabled = False
        self._Notify = None
        if not enabled:
            return
        try:
            import gi
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify
            Notify.init(app_name)
            self._Notify = Notify
            self._enabled = True
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def begin(self, body: str = ""):
        if not self._enabled:
            return None
        try:
            note = self._Notify.Notification.new(SUMMARY, body, _ICON)
            note.show()
            return note
        except Exception:
            return None

    def update(self, handle, body: str) -> None:
        if handle is None:
            return
        try:
            handle.update(SUMMARY, body, _ICON)
            handle.show()
        except Exception:
            pass

    def finish(self, handle, body: str, timeout_ms: int = 3000) -> None:
        if handle is None:
            return
        try:
            handle.update(SUMMARY, body, _ICON)
            handle.set_timeout(timeout_ms)
            handle.show()
        except Exception:
            pass
```

- [ ] **Step 4: Run → PASS** (3 tests). Run: `.venv-gui/bin/pytest tests/mount/test_notify.py -v`

- [ ] **Step 5: Commit** (`feat(mount): best-effort libnotify Notifier`).

---

### Task 2: Notifier + progress on read download-on-open

**Files:** Modify `protondisk/mount/fs.py`; Create `tests/mount/test_fs_notify_read.py`.

**Interfaces:**
- `ProtonDiskFS.__init__(self, disk, ttl=5.0, notifier=None)` — store `self._notifier = notifier or Notifier(enabled=False)`; keep existing `_cache`, `_open_files`, `_next_fh`.
- In the read branch of `open`, wrap the download: `note = self._notifier.begin(f"Opening {basename}…")`; call `self._disk.download(proton_path(path), tmpdir, progress=lambda ph: self._notifier.update(note, f"{ph} {basename}"))`; on success `self._notifier.finish(note, f"Ready: {basename}")`; on error `self._notifier.finish(note, f"Failed: {basename}")` then the existing EIO cleanup.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_fs_notify_read.py`:
```python
import os
from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry


class FakeDisk:
    def __init__(self):
        self._tree = {"/my-files": [Entry("a.txt", "/my-files/a.txt", False, 5, 1.0, "f")]}
    def list(self, path):
        return self._tree.get(path, [])
    def download(self, remote, folder, progress=None):
        if progress:
            progress("Downloading…")
            progress("Decrypting…")
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"hello")


class FakeNotifier:
    def __init__(self):
        self.events = []          # ("begin"|"update"|"finish", body)
    def begin(self, body=""):
        self.events.append(("begin", body)); return {"h": 1}
    def update(self, handle, body):
        self.events.append(("update", body))
    def finish(self, handle, body, timeout_ms=3000):
        self.events.append(("finish", body))


def test_read_open_emits_download_phases_to_notifier():
    note = FakeNotifier()
    fs = ProtonDiskFS(FakeDisk(), notifier=note)
    fh = fs.open("/a.txt", os.O_RDONLY)
    assert fs.read("/a.txt", 5, 0, fh) == b"hello"
    fs.release("/a.txt", fh)
    kinds = [k for k, _ in note.events]
    assert kinds[0] == "begin"
    assert ("update", "Downloading… a.txt") in note.events
    assert ("update", "Decrypting… a.txt") in note.events
    assert kinds[-1] == "finish"


def test_readdir_emits_no_notifications():
    note = FakeNotifier()
    fs = ProtonDiskFS(FakeDisk(), notifier=note)
    fs.readdir("/", None)
    fs.getattr("/a.txt")
    assert note.events == []       # metadata ops are silent
```

- [ ] **Step 2: Run → FAIL** (`TypeError: __init__() got an unexpected keyword argument 'notifier'`). Run: `.venv-gui/bin/pytest tests/mount/test_fs_notify_read.py -v`

- [ ] **Step 3: Implement.** In `protondisk/mount/fs.py`:

Add the import near the top (with the other local imports):
```python
from .notify import Notifier
```
Change `__init__` signature and body:
```python
    def __init__(self, disk, ttl: float = 5.0, notifier=None) -> None:
        self._disk = disk
        self._cache = ListingCache(ttl=ttl)
        self._notifier = notifier or Notifier(enabled=False)
        self._open_files: dict[int, tuple] = {}
        self._next_fh = 1
```
Replace the download block inside `open` (the read path) so it reports progress + notifies. The current read `open` body (after the write-flag/ENOENT/EISDIR guards) becomes:
```python
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        name = os.path.basename(path)
        note = self._notifier.begin(f"Opening {name}…")
        try:
            self._disk.download(
                proton_path(path), tmpdir,
                progress=lambda ph: self._notifier.update(note, f"{ph} {name}"))
            local = os.path.join(tmpdir, name)
            fobj = open(local, "rb")
        except (ProtonDiskError, OSError):
            self._notifier.finish(note, f"Failed: {name}")
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise FuseOSError(errno.EIO)
        self._notifier.finish(note, f"Ready: {name}")
        fh = self._next_fh
        self._next_fh += 1
        self._open_files[fh] = (tmpdir, fobj)
        return fh
```
(Leave `read`/`release`/`getattr`/`readdir`/mutators unchanged in this task.)

- [ ] **Step 4: Run → PASS** (2 tests); full mount suite green (`.venv-gui/bin/pytest tests/mount/ -q`).

- [ ] **Step 5: Commit** (`feat(mount): notify download phases on read open`).

---

### Task 3: Write lifecycle — create/open-write/write/truncate/getattr + upload-on-release  ⚠️ likely the version-13 skip

> This task's bump is expected to hit patch 13 → `scripts/bump-patch.sh` jumps 0.4.13 → **0.4.14** and prints the skip notice. If it does, **this commit's message MUST be `To be sure to be sure!`** (feature described in the body).

**Files:** Modify `protondisk/mount/fs.py`; Create `tests/mount/test_fs_write.py`.

**Interfaces (added / changed on `ProtonDiskFS`):**
- A `_Handle` object replaces the read tuple: `_Handle(tmpdir, fobj, path, writable)` with a mutable `dirty=False`. Read `open`/`read`/`release` are updated to use it.
- `self._write_handles: dict[str, _Handle]` (path → open write handle) added in `__init__`, so `getattr` can report an in-progress/new file.
- `create(path, mode, fi=None) -> int`: new empty buffer `tmpdir/basename` opened `w+b`; register a writable handle; return fh. No upload.
- `open` write branch: `is_write_flags(flags)` → writable. If the path is an existing dir → `EISDIR`. If existing file and NOT `O_TRUNC` → download into the buffer (`r+b`, so partial edits keep bytes); else new/truncate → `w+b`. Register writable handle.
- `write(path, data, offset, fh) -> int`: seek+write into the buffer; set `dirty`; return `len(data)`.
- `truncate(path, length, fh=None) -> int`: with an open handle → truncate its buffer + dirty. Without a handle → download the existing file, truncate, upload replace, cleanup (best-effort).
- `getattr`: if `path` has an open write handle → a writable regular-file stat from `os.stat(buffer)` (`S_IFREG|0o644`, real size/mtime); else the existing listing path.
- `flush(path, fh) -> int` and `fsync(path, datasync, fh) -> int`: if the handle is a dirty writable → upload now (see `_upload_handle`) and clear dirty; return 0.
- `release(path, fh) -> int`: if a dirty writable handle remains → upload (best-effort, swallow error after notifying); then close, rmtree, drop from `_open_files` and `_write_handles`.
- `_upload_handle(h)`: `core.upload(buffer, parent_proton, conflict="replace", progress=cb)` with a "Saving …" notification updated through phases; on success invalidate the parent listing + `finish` "Saved …"; raise `FuseOSError(EIO)` on `ProtonDiskError` (after `finish` "Upload failed").
- `create`/`write`/`truncate` are REMOVED from the `_readonly` alias block (they're real now); `mkdir/unlink/rmdir/rename/chmod/chown/symlink/link` stay `_readonly` (Task 4 implements mkdir/unlink/rmdir/rename).

- [ ] **Step 1: Write the failing test** — `tests/mount/test_fs_write.py`:
```python
import errno, os, stat as stat_mod
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry, TransferResult
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self):
        self.uploads = []          # (local_bytes, parent, conflict)
        self._tree = {"/my-files": [Entry("Dir", "/my-files/Dir", True, None, 1.0, "d")]}
    def list(self, path):
        return self._tree.get(path, [])
    def download(self, remote, folder, progress=None):
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"existing")
    def upload(self, local, parent, *, conflict="skip", progress=None):
        with open(local, "rb") as f:
            data = f.read()
        self.uploads.append((data, parent, conflict, os.path.basename(local)))
        if progress:
            progress("Encrypting…"); progress("Uploading…")
        return TransferResult(1, len(data), 0, 0, [])


class FakeNotifier:
    def __init__(self): self.events = []
    def begin(self, body=""): self.events.append(("begin", body)); return {"h": 1}
    def update(self, h, body): self.events.append(("update", body))
    def finish(self, h, body, timeout_ms=3000): self.events.append(("finish", body))


def _fs():
    return ProtonDiskFS(FakeDisk(), notifier=FakeNotifier())


def test_create_write_release_uploads_replace_under_basename():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/new.txt", 0o644)
    assert fs.write("/new.txt", b"hello ", 0, fh) == 6
    assert fs.write("/new.txt", b"world", 6, fh) == 5
    fs.release("/new.txt", fh)
    assert len(disk.uploads) == 1
    data, parent, conflict, name = disk.uploads[0]
    assert data == b"hello world"
    assert parent == "/my-files" and conflict == "replace" and name == "new.txt"


def test_getattr_reports_buffer_size_for_open_write_handle():
    fs = _fs()
    fh = fs.create("/new.txt", 0o644)
    fs.write("/new.txt", b"1234", 0, fh)
    st = fs.getattr("/new.txt")           # not in the listing yet -> served from handle
    assert st["st_size"] == 4
    assert stat_mod.S_ISREG(st["st_mode"])
    fs.release("/new.txt", fh)


def test_flush_uploads_and_clears_dirty_then_release_is_noop():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/f.txt", 0o644)
    fs.write("/f.txt", b"abc", 0, fh)
    fs.flush("/f.txt", fh)
    fs.release("/f.txt", fh)
    assert len(disk.uploads) == 1         # not re-uploaded on release


def test_truncate_via_handle_changes_uploaded_size():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/t.txt", 0o644)
    fs.write("/t.txt", b"abcdef", 0, fh)
    fs.truncate("/t.txt", 3, fh)
    fs.release("/t.txt", fh)
    assert disk.uploads[0][0] == b"abc"


def test_upload_error_maps_to_eio():
    class BadDisk(FakeDisk):
        def upload(self, local, parent, *, conflict="skip", progress=None):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk(), notifier=FakeNotifier())
    fh = fs.create("/x.txt", 0o644)
    fs.write("/x.txt", b"z", 0, fh)
    with pytest.raises(FuseOSError) as ei:
        fs.flush("/x.txt", fh)
    assert ei.value.errno == errno.EIO
    fs.release("/x.txt", fh)              # cleanup still succeeds


def test_upload_notification_phases():
    note = FakeNotifier()
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=note)
    fh = fs.create("/n.txt", 0o644)
    fs.write("/n.txt", b"q", 0, fh)
    fs.release("/n.txt", fh)
    assert note.events[0][0] == "begin"
    assert ("update", "Encrypting… n.txt") in note.events
    assert ("update", "Uploading… n.txt") in note.events
    assert note.events[-1][0] == "finish"
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... 'create'` / write flag rejected). Run: `.venv-gui/bin/pytest tests/mount/test_fs_write.py -v`

- [ ] **Step 3: Implement.** Full changes to `protondisk/mount/fs.py`:

Add a handle class above `ProtonDiskFS`:
```python
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
```
Add `self._write_handles: dict[str, _Handle] = {}` in `__init__`.

Add a registration helper and replace `open`/`read`/`release`, and add `create`/`write`/`truncate`/`flush`/`fsync`/`_upload_handle`. Replace the whole `# ---- download-on-open ----` section and the `getattr`/mutator wiring as follows:
```python
    # ---- handle registry ----
    def _register(self, tmpdir, fobj, path, writable) -> int:
        h = _Handle(tmpdir, fobj, path, writable)
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
            else:
                fobj = open(local, "w+b")
        except (ProtonDiskError, OSError):
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise FuseOSError(errno.EIO)
        return self._register(tmpdir, fobj, path, writable=True)

    def create(self, path, mode, fi=None):
        tmpdir = tempfile.mkdtemp(prefix="protondisk-mnt-")
        fobj = open(os.path.join(tmpdir, os.path.basename(path)), "w+b")
        return self._register(tmpdir, fobj, path, writable=True)

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
        except ProtonDiskError:
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
```
Update `getattr` to consult open write handles first:
```python
    def getattr(self, path, fh=None):
        if path == "/":
            return root_stat_dict(time.time())
        h = self._write_handles.get(path)
        if h is not None:
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
```
Add `import stat as stat_mod` to the imports. In the read-only alias block, REMOVE `write`, `create`, `truncate` (now real); keep:
```python
    mkdir = unlink = rmdir = _readonly
    rename = chmod = chown = symlink = link = _readonly
```

- [ ] **Step 4: Run → PASS** (6 tests); full mount suite green.

- [ ] **Step 5: Commit** — `ver=$(scripts/bump-patch.sh)`. **If the stderr skip notice fired (0.4.13 skipped), the commit subject MUST be `To be sure to be sure!`** with the body `feat(mount): write lifecycle — create/write/truncate/upload-on-release. Patch 0.4.13 skipped per project rule.` + trailer. Otherwise use `feat(mount): write lifecycle (create/write/truncate/upload-on-release) (v$ver)` + trailer. `git add protondisk/mount/fs.py tests/mount/test_fs_write.py VERSION`; push.

---

### Task 4: Namespace ops — mkdir, unlink/rmdir (trash), rename

**Files:** Modify `protondisk/mount/fs.py`; Create `tests/mount/test_fs_namespace.py`.

**Interfaces (replace the corresponding `_readonly` aliases with real methods):**
- `mkdir(path, mode) -> int`: `core.mkdir(path)` (fuse `/A/B` → the core splits into parent+name; `mkdir` takes the full proton path — use `proton_path(path)`); invalidate the parent listing; return 0. On `ProtonDiskError` → `EIO`.
- `unlink(path) -> int` and `rmdir(path) -> int`: `core.trash(proton_path(path))`; invalidate parent; return 0; error → `EIO`.
- `rename(old, new) -> int`: if `new`'s basename already exists in `new`'s parent listing → `FuseOSError(errno.EEXIST)`. Else: same parent → `core.rename(proton_path(old), basename(new))`; different parent → `core.move(proton_path(old), proton_path(parent(new)))`, then if `basename(new) != basename(old)` also `core.rename(<moved path>, basename(new))`. Invalidate both parents. Error → `EIO`.
- Keep `chmod/chown/symlink/link` as `_readonly` (EROFS — Proton has no equivalent).

- [ ] **Step 1: Write the failing test** — `tests/mount/test_fs_namespace.py`:
```python
import errno
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self):
        self.calls = []
        self._tree = {
            "/my-files": [
                Entry("a.txt", "/my-files/a.txt", False, 5, 1.0, "f"),
                Entry("Dir", "/my-files/Dir", True, None, 1.0, "d"),
                Entry("b.txt", "/my-files/b.txt", False, 3, 1.0, "g"),
            ],
            "/my-files/Dir": [],
        }
    def list(self, path):
        return self._tree.get(path, [])
    def mkdir(self, path):
        self.calls.append(("mkdir", path))
    def trash(self, path):
        self.calls.append(("trash", path))
    def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
    def move(self, src, target_parent):
        self.calls.append(("move", src, target_parent))


def test_mkdir_calls_core():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    assert fs.mkdir("/NewDir", 0o755) == 0
    assert ("mkdir", "/my-files/NewDir") in disk.calls


def test_unlink_and_rmdir_trash():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.unlink("/a.txt"); fs.rmdir("/Dir")
    assert ("trash", "/my-files/a.txt") in disk.calls
    assert ("trash", "/my-files/Dir") in disk.calls


def test_rename_same_dir():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.rename("/a.txt", "/renamed.txt")
    assert ("rename", "/my-files/a.txt", "renamed.txt") in disk.calls


def test_rename_into_other_dir_uses_move():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.rename("/a.txt", "/Dir/a.txt")
    assert ("move", "/my-files/a.txt", "/my-files/Dir") in disk.calls


def test_rename_onto_existing_name_is_eexist():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    with pytest.raises(FuseOSError) as ei:
        fs.rename("/a.txt", "/b.txt")     # b.txt already exists
    assert ei.value.errno == errno.EEXIST
    assert all(c[0] != "rename" for c in disk.calls)  # nothing attempted


def test_core_error_maps_to_eio():
    class BadDisk(FakeDisk):
        def trash(self, path):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.unlink("/a.txt")
    assert ei.value.errno == errno.EIO
```

- [ ] **Step 2: Run → FAIL** (mkdir raises EROFS, not calling core). Run: `.venv-gui/bin/pytest tests/mount/test_fs_namespace.py -v`

- [ ] **Step 3: Implement.** In `protondisk/mount/fs.py`, remove `mkdir`, `unlink`, `rmdir`, `rename` from the `_readonly` block (leaving `chmod = chown = symlink = link = _readonly`), and add:
```python
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
        old_parent = os.path.dirname(old) or "/"
        new_parent = os.path.dirname(new) or "/"
        old_name = os.path.basename(old)
        new_name = os.path.basename(new)
        if new_name in self._entry_names(new_parent):
            raise FuseOSError(errno.EEXIST)  # Proton won't overwrite
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
```
(Because `rmdir = unlink`, `rmdir("/Dir")` trashes the folder — Proton's trash handles folders. Keep the alias.)

- [ ] **Step 4: Run → PASS** (6 tests); full mount suite green.

- [ ] **Step 5: Commit** (`feat(mount): mkdir, trash (unlink/rmdir), rename/move`).

---

### Task 5: Mount read-write + CLI wording; pass a Notifier

**Files:** Modify `protondisk/mount/mounter.py`, `protondisk/cli.py`; Modify `tests/mount/test_mount_cli.py` (message assertion).

**Interfaces:**
- `mounter.mount(disk, mountpoint, *, ttl=5.0, foreground=True)`: drop `ro=True`; construct `ProtonDiskFS(disk, ttl=ttl, notifier=Notifier())` (a real Notifier — best-effort) and mount **read-write**: `FUSE(fs, mountpoint, foreground=foreground, nothreads=True, allow_other=False)`.
- `cli._cmd_mount`: change the printed line to `Mounted /my-files (read-write) at {mountpoint} — press Ctrl-C to unmount`.
- Update the existing CLI test's success-message assertion to match (still asserts the mountpoint appears; loosen any exact-string check).

- [ ] **Step 1: Adjust the failing test.** In `tests/mount/test_mount_cli.py`, `test_mount_when_authed_calls_mounter` already asserts the mountpoint is in stdout — keep that. Add:
```python
def test_mount_message_mentions_read_write(capsys):
    from protondisk.cli import _cmd_mount
    from protondisk.core.models import AuthStatus

    class D:
        def auth_status(self): return AuthStatus(True, "u@pm.me")
    class M:
        def mount(self, disk, mountpoint, *, ttl=5.0, foreground=True): pass
        def unmount(self, mp): return True
    _cmd_mount(D(), "/tmp/mp", mounter=M())
    assert "read-write" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run → FAIL** (message lacks "read-write"). Run: `.venv-gui/bin/pytest tests/mount/test_mount_cli.py -v`

- [ ] **Step 3: Implement.** `protondisk/mount/mounter.py`:
```python
from fuse import FUSE

from .fs import ProtonDiskFS
from .notify import Notifier
```
```python
def mount(disk, mountpoint: str, *, ttl: float = 5.0, foreground: bool = True) -> None:
    os.makedirs(mountpoint, exist_ok=True)
    fs = ProtonDiskFS(disk, ttl=ttl, notifier=Notifier())
    FUSE(fs, mountpoint, foreground=foreground, nothreads=True)
```
In `protondisk/cli.py` `_cmd_mount`, change the print to:
```python
    print(f"Mounted /my-files (read-write) at {mountpoint} — press Ctrl-C to unmount")
```

- [ ] **Step 4: Run → PASS**; FULL suite `.venv-gui/bin/pytest -q` green.

Controller live verification (NOT the implementer): mount read-write at `/tmp/pdrw`; `cp` a local file in and confirm it appears on the Drive (`proton-drive filesystem list`); `mkdir` a folder; `echo >>`/save edit a file; `rm` a file (→ trash); `mv` (rename) a file; confirm a notification appeared for a transfer; unmount; clean up the test files from the Drive.

- [ ] **Step 5: Commit** (`feat(mount): mount read-write with a live Notifier`).

---

## Increment Completion — "Bump minor" to 0.6.0

After all 5 tasks pass, when the user says **"Bump minor"**: update `CHANGELOG.md` (0.6.0 — read-write mount + notifications) and `README.md` (mount is now read-write; note the copy-in/save support, the rename-over-existing limitation, and that transfer progress shows as desktop notifications); set `VERSION` to `0.6.0`; commit to `dev`, merge `dev` → `main`, push both, tag `v0.6.0`.

## Self-Review

**Spec coverage (design §4-§9):** Notifier (T1); read download notification+progress (T2); create/open-write/write/truncate/getattr-from-buffer/flush/release upload-replace + upload notification + cache invalidation (T3); mkdir/unlink/rmdir→trash/rename(+move, EEXIST) (T4); read-write mount flag + real Notifier + CLI wording (T5). Rename-over-existing → EEXIST (T4). Core errors → EIO (T3/T4). Notifications only for transfers (T2/T3 assert readdir/getattr are silent). All present.

**Placeholder scan:** every step has complete code; no TBDs. The Task-3 "version-13 skip" note is a real branch of the bump script, not a placeholder.

**Type/name consistency:** `ProtonDiskFS(disk, ttl, notifier)`, `_Handle(tmpdir, fobj, path, writable)` + `.dirty`/`.local()`, `_register`, `_write_handles`, `_upload_handle`, `Notifier.begin/update/finish`, `FakeNotifier`/`FakeDisk` with `list/download(progress=)/upload(conflict=,progress=)/mkdir/trash/rename/move` are consistent across tasks. Read `open`/`read`/`release` are refactored to `_Handle` in Task 3 and all later handle users match. `rmdir = unlink` alias intentional.

**Risk notes:** whole-file re-upload per save (documented); rename-over-existing unsupported (EEXIST, documented); `release` swallows a late upload error after notifying (can't propagate meaningfully at release; flush surfaces it for well-behaved apps); standalone `truncate` without an fh does a download→truncate→upload round-trip. Live-verified by the controller before the 0.6.0 merge.

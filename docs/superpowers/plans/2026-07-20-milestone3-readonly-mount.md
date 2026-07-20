# ProtonDisk Milestone 3 (increment 1) — Read-only FUSE Mount

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount Proton Drive `/my-files` as a **read-only** local disk (browse in any file manager, open/copy files out), built on `protondisk.core`.

**Architecture:** New `protondisk/mount/` package using **fusepy** (pure-Python, libfuse2). Pure logic (path mapping, stat building, TTL cache) lives in fuse-free modules and is unit-tested anywhere; the `ProtonDiskFS(fuse.Operations)` class and mounter are tested by calling their methods directly with a fake core (no kernel mount). Mount root maps to Proton `/my-files`. `getattr` is served from the parent directory's cached listing so an `ls` of N files costs one `core.list`, not N `core.stat`s (fair-use).

**Tech Stack:** Python 3.12+, **fusepy**, stdlib (`os`, `stat`, `errno`, `tempfile`, `shutil`, `time`, `subprocess`), `pytest`.

## Global Constraints

- **Environment:** fusepy is pure-Python and already installed in **`.venv-gui`** (the full dev venv: pytest + editable protondisk + fusepy). Run ALL mount tests with **`.venv-gui/bin/pytest`**. (`fs.py`/`mounter.py` import `fuse`, so their tests need fusepy; `translate.py`/`cache.py` are fuse-free.) libfuse2 + `/dev/fuse` are present for live mount verification.
- **Layering:** `protondisk/mount/*` imports only `fuse`, stdlib, and `protondisk.core`. NEVER `subprocess` to the `proton-drive` binary (only `mounter.unmount` may call `fusermount`). The core stays the single Drive dependency point.
- **Read-only:** every mutating FUSE op raises `FuseOSError(errno.EROFS)`; `open` rejects write flags; FUSE mounted with `ro=True`.
- **Fair-use:** `getattr`/`readdir` go through the TTL listing cache; only genuine misses call the core.
- **Versioning (project GIT rules):** `VERSION` is the single source of truth; each task commit runs `scripts/bump-patch.sh` (skips patch 13 → commit message `To be sure to be sure!` if the skip notice fires) and pushes to `dev`. A repo-local git identity is set (author = mbeulens), but the commit message MUST still end with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer. Increment done → **"Bump minor" → 0.5.0**.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'` (belt and suspenders) + the trailer.
- **GENUINE verification:** actually run tests and paste REAL output; never fabricate. Do NOT run a blocking `protondisk mount` in a subagent — the controller live-verifies the real mount.

## File Structure

```
protondisk/mount/
├── __init__.py
├── translate.py   # proton_path, is_write_flags, stat_dict, root_stat_dict (fuse-free)
├── cache.py       # ListingCache (TTL, fuse-free)
├── fs.py          # ProtonDiskFS(fuse.Operations)
└── mounter.py     # mount() / unmount()
protondisk/cli.py  # + `mount` / `unmount` subcommands (modify)
pyproject.toml     # mount extra -> fusepy (modify)
tests/mount/
├── test_translate.py  test_cache.py  test_fs_read.py  test_fs_download.py  test_mount_cli.py
```

---

### Task 1: Package skeleton, `mount` dependency, and `translate.py`

**Files:** Create `protondisk/mount/__init__.py`, `protondisk/mount/translate.py`, `tests/mount/test_translate.py`; Modify `pyproject.toml`.

**Interfaces (`translate.py`, all pure, no `fuse` import):**
- `ROOT = "/my-files"`.
- `proton_path(fuse_path: str) -> str`: `"/"`→`"/my-files"`; `"/Reports/q3.pdf"`→`"/my-files/Reports/q3.pdf"`.
- `is_write_flags(flags: int) -> bool`: True if `flags & os.O_ACCMODE` is `O_WRONLY`/`O_RDWR`, or any of `O_APPEND`/`O_CREAT`/`O_TRUNC` set.
- `stat_dict(entry, now: float) -> dict`: dirs `S_IFDIR|0o555` nlink 2 size 0; files `S_IFREG|0o444` nlink 1 size `entry.size or 0`; `st_mtime/ctime/atime` = `entry.mtime` if not None else `now`; `st_uid/st_gid` = current.
- `root_stat_dict(now: float) -> dict`: a directory stat for the mount root.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_translate.py`:
```python
import os, stat as stat_mod
from protondisk.mount.translate import proton_path, is_write_flags, stat_dict, root_stat_dict
from protondisk.core.models import Entry


def test_proton_path():
    assert proton_path("/") == "/my-files"
    assert proton_path("/Reports") == "/my-files/Reports"
    assert proton_path("/Reports/q3.pdf") == "/my-files/Reports/q3.pdf"


def test_is_write_flags():
    assert is_write_flags(os.O_RDONLY) is False
    assert is_write_flags(os.O_WRONLY) is True
    assert is_write_flags(os.O_RDWR) is True
    assert is_write_flags(os.O_RDONLY | os.O_TRUNC) is True
    assert is_write_flags(os.O_RDONLY | os.O_APPEND) is True


def test_stat_dict_file_and_dir():
    f = Entry("a.txt", "/my-files/a.txt", False, 95, 1720000000.0, "u")
    sf = stat_dict(f, now=1.0)
    assert sf["st_mode"] == (stat_mod.S_IFREG | 0o444)
    assert sf["st_size"] == 95 and sf["st_nlink"] == 1 and sf["st_mtime"] == 1720000000.0
    d = Entry("Dir", "/my-files/Dir", True, None, None, "u")
    sd = stat_dict(d, now=7.0)
    assert sd["st_mode"] == (stat_mod.S_IFDIR | 0o555)
    assert sd["st_size"] == 0 and sd["st_nlink"] == 2 and sd["st_mtime"] == 7.0  # mtime None -> now


def test_root_stat_dict_is_dir():
    r = root_stat_dict(now=3.0)
    assert r["st_mode"] == (stat_mod.S_IFDIR | 0o555) and r["st_mtime"] == 3.0
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: protondisk.mount`). Run: `.venv-gui/bin/pytest tests/mount/test_translate.py -v`

- [ ] **Step 3: Implement.** Ensure fusepy is available (idempotent): `.venv-gui/bin/pip install -q fusepy`.

`protondisk/mount/__init__.py`:
```python
"""ProtonDisk read-only FUSE mount (fusepy)."""
```
`protondisk/mount/translate.py`:
```python
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
    mtime = entry.mtime if entry.mtime is not None else now
    if entry.is_dir:
        mode, nlink, size = stat_mod.S_IFDIR | 0o555, 2, 0
    else:
        mode, nlink, size = stat_mod.S_IFREG | 0o444, 1, (entry.size or 0)
    return {
        "st_mode": mode, "st_nlink": nlink, "st_size": size,
        "st_mtime": mtime, "st_ctime": mtime, "st_atime": mtime,
        "st_uid": os.getuid(), "st_gid": os.getgid(),
    }


def root_stat_dict(now: float) -> dict:
    return {
        "st_mode": stat_mod.S_IFDIR | 0o555, "st_nlink": 2, "st_size": 0,
        "st_mtime": now, "st_ctime": now, "st_atime": now,
        "st_uid": os.getuid(), "st_gid": os.getgid(),
    }
```
`pyproject.toml`: change the `mount` extra from `pyfuse3` to `fusepy`:
```toml
mount = ["fusepy"]
```

- [ ] **Step 4: Run → PASS** (4 tests). Run: `.venv-gui/bin/pytest tests/mount/test_translate.py -v`

- [ ] **Step 5: Commit** (`ver=$(scripts/bump-patch.sh)`; add the four files; message `feat(mount): package skeleton, fusepy dep, path/stat translation (v$ver)` + trailer; push).

---

### Task 2: `cache.py` — TTL listing cache

**Files:** Create `protondisk/mount/cache.py`, `tests/mount/test_cache.py`.

**Interfaces (`cache.py`, fuse-free):**
- `ListingCache(ttl: float = 5.0, clock=time.monotonic)`:
  - `get(path) -> list | None`: cached entries if present and not expired (expired entry is dropped and returns None).
  - `put(path, entries) -> None`: store with `expires = clock() + ttl`.
  - `invalidate(path=None)`: drop one path, or all when None.
- `clock` is injectable so tests use a fake monotonic clock.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_cache.py`:
```python
from protondisk.mount.cache import ListingCache


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_put_get_hit():
    c = ListingCache(ttl=5.0, clock=FakeClock())
    c.put("/p", ["a", "b"])
    assert c.get("/p") == ["a", "b"]


def test_miss_returns_none():
    assert ListingCache(clock=FakeClock()).get("/nope") is None


def test_expiry():
    clk = FakeClock()
    c = ListingCache(ttl=5.0, clock=clk)
    c.put("/p", ["a"])
    clk.t = 4.9
    assert c.get("/p") == ["a"]      # still fresh
    clk.t = 5.0
    assert c.get("/p") is None       # expired (dropped)
    assert c.get("/p") is None


def test_invalidate():
    clk = FakeClock()
    c = ListingCache(clock=clk)
    c.put("/a", [1]); c.put("/b", [2])
    c.invalidate("/a")
    assert c.get("/a") is None and c.get("/b") == [2]
    c.invalidate()
    assert c.get("/b") is None
```

- [ ] **Step 2: Run → FAIL.** Run: `.venv-gui/bin/pytest tests/mount/test_cache.py -v`

- [ ] **Step 3: Implement** — `protondisk/mount/cache.py`:
```python
"""A small TTL cache of directory listings (fuse-free)."""
from __future__ import annotations

import time


class ListingCache:
    def __init__(self, ttl: float = 5.0, clock=time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._data: dict[str, tuple] = {}

    def get(self, path: str):
        hit = self._data.get(path)
        if hit is None:
            return None
        entries, expires = hit
        if self._clock() >= expires:
            self._data.pop(path, None)
            return None
        return entries

    def put(self, path: str, entries) -> None:
        self._data[path] = (entries, self._clock() + self._ttl)

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._data.clear()
        else:
            self._data.pop(path, None)
```

- [ ] **Step 4: Run → PASS** (4 tests). Run: `.venv-gui/bin/pytest tests/mount/test_cache.py -v`

- [ ] **Step 5: Commit** (`feat(mount): TTL listing cache`).

---

### Task 3: `fs.py` — read metadata (getattr, readdir) + read-only enforcement

**Files:** Create `protondisk/mount/fs.py`, `tests/mount/test_fs_read.py`.

**Interfaces:**
- `ProtonDiskFS(fuse.Operations)`:
  - `__init__(self, disk, ttl=5.0)` — stores the core `disk`, a `ListingCache(ttl)`, an empty `_open_files: dict` and `_next_fh = 1` (used in Task 4).
  - `_listing(self, proton_dir) -> list[Entry]`: cache-through to `disk.list`.
  - `_find_entry(self, fuse_path)`: look up the basename in the parent dir's cached listing; return the `Entry` or `None`.
  - `getattr(self, path, fh=None)`: `"/"` → `root_stat_dict(time.time())`; else `_find_entry` → `stat_dict(entry, time.time())`; missing → `FuseOSError(errno.ENOENT)`.
  - `readdir(self, path, fh)`: `['.', '..', *names]` from `_listing(proton_path(path))`.
  - `statfs(self, path)`: static dict (`f_bsize` 4096, `f_namemax` 255, zeros elsewhere).
  - Read-only mutators — `write`, `create`, `mkdir`, `unlink`, `rmdir`, `rename`, `truncate`, `chmod`, `chown`, `symlink`, `link` — all raise `FuseOSError(errno.EROFS)`.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_fs_read.py`:
```python
import errno
import stat as stat_mod
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry


class FakeDisk:
    def __init__(self):
        self.list_calls = []
        self._tree = {
            "/my-files": [
                Entry("Reports", "/my-files/Reports", True, None, 1720000000.0, "d"),
                Entry("a.txt", "/my-files/a.txt", False, 95, 1720000001.0, "f"),
            ],
            "/my-files/Reports": [
                Entry("q3.pdf", "/my-files/Reports/q3.pdf", False, 10, 1720000002.0, "g"),
            ],
        }

    def list(self, path):
        self.list_calls.append(path)
        return self._tree.get(path, [])


def test_readdir_root():
    fs = ProtonDiskFS(FakeDisk())
    assert set(fs.readdir("/", None)) == {".", "..", "Reports", "a.txt"}


def test_getattr_root_is_dir():
    fs = ProtonDiskFS(FakeDisk())
    st = fs.getattr("/")
    assert st["st_mode"] == (stat_mod.S_IFDIR | 0o555)


def test_getattr_file_from_parent_listing_is_one_list_call():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    st = fs.getattr("/a.txt")
    assert st["st_mode"] == (stat_mod.S_IFREG | 0o444)
    assert st["st_size"] == 95
    # getattr of two entries in the same dir must not multiply list() calls (cache)
    fs.getattr("/Reports")
    assert disk.list_calls.count("/my-files") == 1


def test_getattr_missing_raises_enoent():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.getattr("/nope.txt")
    assert ei.value.errno == errno.ENOENT


def test_readonly_ops_raise_erofs():
    fs = ProtonDiskFS(FakeDisk())
    for call in (lambda: fs.mkdir("/x", 0o755),
                 lambda: fs.unlink("/a.txt"),
                 lambda: fs.rename("/a.txt", "/b.txt"),
                 lambda: fs.write("/a.txt", b"x", 0, 1),
                 lambda: fs.create("/x", 0o644)):
        with pytest.raises(FuseOSError) as ei:
            call()
        assert ei.value.errno == errno.EROFS
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: protondisk.mount.fs`). Run: `.venv-gui/bin/pytest tests/mount/test_fs_read.py -v`

- [ ] **Step 3: Implement** — `protondisk/mount/fs.py`:
```python
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

    # ---- read-only enforcement ----
    def _readonly(self, *args, **kwargs):
        raise FuseOSError(errno.EROFS)

    write = create = mkdir = unlink = rmdir = _readonly
    rename = truncate = chmod = chown = symlink = link = _readonly
```

- [ ] **Step 4: Run → PASS** (5 tests). Run: `.venv-gui/bin/pytest tests/mount/test_fs_read.py -v`

- [ ] **Step 5: Commit** (`feat(mount): read-only getattr/readdir with listing cache`).

---

### Task 4: `fs.py` — download-on-open (open, read, release)

**Files:** Modify `protondisk/mount/fs.py`; Create `tests/mount/test_fs_download.py`.

**Interfaces (added to `ProtonDiskFS`):**
- `open(self, path, flags)`: `is_write_flags(flags)` → `FuseOSError(errno.EROFS)`. `_find_entry` missing → `ENOENT`; a directory → `EISDIR`. Else make a temp dir, `disk.download(proton_path(path), tmpdir)` (on `ProtonDiskError` → clean up + `FuseOSError(errno.EIO)`), open `tmpdir/basename` `"rb"`, store `_open_files[fh] = (tmpdir, file)`, return a new integer `fh`.
- `read(self, path, size, offset, fh)`: `seek(offset)` + `read(size)` from the stored file.
- `release(self, path, fh)`: close the file, `shutil.rmtree(tmpdir)`, drop the handle, return 0.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_fs_download.py`:
```python
import errno, os
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self, contents=b"hello proton"):
        self._contents = contents
        self.downloads = []
        self._tree = {"/my-files": [
            Entry("a.txt", "/my-files/a.txt", False, len(contents), 1.0, "f"),
            Entry("Dir", "/my-files/Dir", True, None, 1.0, "d"),
        ]}

    def list(self, path):
        return self._tree.get(path, [])

    def download(self, remote, folder):
        self.downloads.append((remote, folder))
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(self._contents)


def test_open_read_release_round_trip():
    disk = FakeDisk(b"hello proton")
    fs = ProtonDiskFS(disk)
    fh = fs.open("/a.txt", os.O_RDONLY)
    assert disk.downloads == [("/my-files/a.txt", fs._open_files[fh][0])]
    assert fs.read("/a.txt", 5, 0, fh) == b"hello"
    assert fs.read("/a.txt", 100, 6, fh) == b"proton"
    tmpdir = fs._open_files[fh][0]
    fs.release("/a.txt", fh)
    assert fh not in fs._open_files
    assert not os.path.exists(tmpdir)   # temp cleaned up


def test_open_write_flag_is_erofs():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/a.txt", os.O_WRONLY)
    assert ei.value.errno == errno.EROFS


def test_open_directory_is_eisdir():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/Dir", os.O_RDONLY)
    assert ei.value.errno == errno.EISDIR


def test_open_download_failure_is_eio():
    class BadDisk(FakeDisk):
        def download(self, remote, folder):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/a.txt", os.O_RDONLY)
    assert ei.value.errno == errno.EIO
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... 'open'`). Run: `.venv-gui/bin/pytest tests/mount/test_fs_download.py -v`

- [ ] **Step 3: Implement** — append to `ProtonDiskFS` (before the `_readonly` block):
```python
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
```

- [ ] **Step 4: Run → PASS** (4 tests); full mount suite green (`.venv-gui/bin/pytest tests/mount/ -v`).

- [ ] **Step 5: Commit** (`feat(mount): download-on-open read path`).

---

### Task 5: `mounter.py` + `protondisk mount` / `unmount` CLI

**Files:** Create `protondisk/mount/mounter.py`, `tests/mount/test_mount_cli.py`; Modify `protondisk/cli.py`.

**Interfaces:**
- `mounter.mount(disk, mountpoint, *, ttl=5.0, foreground=True) -> None`: `os.makedirs(mountpoint, exist_ok=True)`; `FUSE(ProtonDiskFS(disk, ttl=ttl), mountpoint, foreground=foreground, ro=True, nothreads=True)`.
- `mounter.unmount(mountpoint) -> bool`: run `fusermount3 -u` (or `fusermount -u`) via `subprocess`; return True on success.
- `mounter.default_mountpoint() -> str`: `os.path.expanduser("~/ProtonDisk")`.
- `cli.py`: `mount [MOUNTPOINT]` and `unmount [MOUNTPOINT]` subparsers. `main` handles them via injectable seams so they're testable:
  - `_cmd_mount(disk, mountpoint, *, mounter=mounter) -> int`: `disk.auth_status()`; if not `logged_in` → print `error: not signed in — run 'protondisk auth-status'` to stderr, return 1; else print the "Mounted … Ctrl-C to unmount" line and call `mounter.mount(disk, mountpoint)`, return 0.
  - `_cmd_unmount(mountpoint, *, mounter=mounter) -> int`: return 0 if `mounter.unmount(mountpoint)` else 1.
  - Wire the subcommands to these. `mount`/`unmount` resolve the mountpoint arg or `mounter.default_mountpoint()`. `mount` constructs `ProtonDisk()` (like the other non-version commands) unless a `disk` is injected.

- [ ] **Step 1: Write the failing test** — `tests/mount/test_mount_cli.py`:
```python
from protondisk.cli import _cmd_mount, _cmd_unmount
from protondisk.core.models import AuthStatus


class FakeDisk:
    def __init__(self, logged_in=True):
        self._st = AuthStatus(logged_in=logged_in, account="u@pm.me")
    def auth_status(self):
        return self._st


class FakeMounter:
    def __init__(self, unmount_ok=True):
        self.mounted = None
        self.unmounted = None
        self._unmount_ok = unmount_ok
    def mount(self, disk, mountpoint, *, ttl=5.0, foreground=True):
        self.mounted = mountpoint
    def unmount(self, mountpoint):
        self.unmounted = mountpoint
        return self._unmount_ok


def test_mount_requires_auth(capsys):
    m = FakeMounter()
    rc = _cmd_mount(FakeDisk(logged_in=False), "/tmp/mp", mounter=m)
    assert rc == 1
    assert "sign" in capsys.readouterr().err.lower()
    assert m.mounted is None            # never mounted while logged out


def test_mount_when_authed_calls_mounter(capsys):
    m = FakeMounter()
    rc = _cmd_mount(FakeDisk(logged_in=True), "/tmp/mp", mounter=m)
    assert rc == 0
    assert m.mounted == "/tmp/mp"
    assert "/tmp/mp" in capsys.readouterr().out


def test_unmount_success_and_failure():
    ok = FakeMounter(unmount_ok=True)
    assert _cmd_unmount("/tmp/mp", mounter=ok) == 0 and ok.unmounted == "/tmp/mp"
    bad = FakeMounter(unmount_ok=False)
    assert _cmd_unmount("/tmp/mp", mounter=bad) == 1
```

- [ ] **Step 2: Run → FAIL** (`ImportError: cannot import name '_cmd_mount'`). Run: `.venv-gui/bin/pytest tests/mount/test_mount_cli.py -v`

- [ ] **Step 3: Implement.**

`protondisk/mount/mounter.py`:
```python
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
```

In `protondisk/cli.py`:
- Add subparsers in `_build_parser()` after `gui`:
```python
    mnt = sub.add_parser("mount", help="mount Proton Drive as a read-only disk")
    mnt.add_argument("mountpoint", nargs="?", default=None)
    umnt = sub.add_parser("unmount", help="unmount the Proton Drive disk")
    umnt.add_argument("mountpoint", nargs="?", default=None)
```
- Add the command functions (module level):
```python
def _cmd_mount(disk, mountpoint, *, mounter=None) -> int:
    import sys
    from .mount import mounter as _mounter
    mounter = mounter or _mounter
    status = disk.auth_status()
    if not status.logged_in:
        print("error: not signed in — run 'protondisk auth-status' / 'auth login'",
              file=sys.stderr)
        return 1
    print(f"Mounted /my-files at {mountpoint} — press Ctrl-C to unmount")
    mounter.mount(disk, mountpoint)
    return 0


def _cmd_unmount(mountpoint, *, mounter=None) -> int:
    from .mount import mounter as _mounter
    mounter = mounter or _mounter
    return 0 if mounter.unmount(mountpoint) else 1
```
- In `main()`, after the `gui` branch and before `disk = disk or ProtonDisk()`, handle unmount (no disk needed), and handle mount (needs disk):
```python
    if args.command == "unmount":
        from .mount import mounter as _mounter
        return _cmd_unmount(args.mountpoint or _mounter.default_mountpoint())
    if args.command == "mount":
        from .mount import mounter as _mounter
        mp = args.mountpoint or _mounter.default_mountpoint()
        return _cmd_mount(disk or ProtonDisk(), mp)
```
(Keep the existing `version` early-return above; the `disk = disk or ProtonDisk()` line for auth-status/ls stays below.)

- [ ] **Step 4: Run → PASS** (3 tests); FULL suite `.venv-gui/bin/pytest -q` green.

Controller live verification (NOT run by the implementer): actually `protondisk mount /tmp/pdmnt` in the background, `ls /tmp/pdmnt`, `cat` a small file and compare to a direct `core.download`, then `protondisk unmount /tmp/pdmnt`.

- [ ] **Step 5: Commit** (`feat(mount): mount/unmount lifecycle and CLI commands`).

---

## Increment Completion — "Bump minor" to 0.5.0

After all 5 tasks pass, when the user says **"Bump minor"**: update `CHANGELOG.md` (0.5.0 — read-only FUSE mount) and `README.md` (status table + `protondisk mount` usage + libfuse2 prerequisite); set `VERSION` to `0.5.0`; commit to `dev`, merge `dev` → `main`, push both, tag `v0.5.0`.

## Self-Review

**Spec coverage (design §3-§8):** translate/path-mapping + stat + write-flags (T1), TTL cache (T2), getattr-from-listing + readdir + read-only EROFS (T3), download-on-open read path (T4), mount/unmount lifecycle + CLI + auth gate (T5). fusepy dep (T1). getattr served from parent listing so an `ls` is one `list()` — asserted in T3. All present.

**Placeholder scan:** every step has complete code; no TBDs.

**Type/name consistency:** `ProtonDiskFS(disk, ttl)`, `proton_path`, `is_write_flags`, `stat_dict`/`root_stat_dict`, `ListingCache(ttl, clock)`, `mounter.mount/unmount/default_mountpoint`, `_cmd_mount/_cmd_unmount` are consistent across tasks. `FakeDisk` in mount tests provides `list`/`download`/`auth_status` as each task needs. Read-only mutators all route through `_readonly`.

**Note:** mount tests import `fuse` (fs.py/mounter.py) so they run under `.venv-gui` (fusepy installed). The live mount is controller-verified; subagents never run a blocking `protondisk mount`.

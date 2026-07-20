# ProtonDisk Milestone 3 — Read-only FUSE Mount (Design)

**Date:** 2026-07-20
**Status:** Approved (brainstorming complete)
**Scope:** Increment 1 of Milestone 3 — a **read-only** mount (→ 0.5.0). Read-write is a
later increment (→ 0.6.0).

## 1. Summary

Mount Proton Drive as a **read-only** local disk so it can be browsed in any file manager
or terminal, and files opened/copied *out*. Built on the existing `protondisk.core`
façade; the mount never invokes the `proton-drive` binary directly.

Mount root maps to Proton **`/my-files`** (your main files). Shared-with-me / trash /
devices are excluded from this increment.

## 2. Feasibility (captured from this machine)

- `/dev/fuse` present and world-writable → non-root mounts work.
- `fusermount` + `fusermount3` present; **libfuse2 (2.9.9)** and libfuse3 installed.
- **No Python FUSE lib and no libfuse dev headers.** Therefore **pyfuse3 cannot build**
  here (needs libfuse3-dev + Cython). **fusepy** — pure-Python, ctypes over
  `libfuse.so.2` — installs cleanly and loads. **Decision: use fusepy** (overrides the
  original design's pyfuse3 choice). fusepy is synchronous, which fits our blocking,
  subprocess-based core.

## 3. Architecture

New package `protondisk/mount/`:

```
protondisk/mount/
├── __init__.py
├── cache.py     # TTL listing cache (pure, gi-free, unit-tested)
├── fs.py        # ProtonDiskFS(fuse.Operations) — read-only ops
└── mounter.py   # mount()/unmount() helpers
protondisk/cli.py  # + `mount` / `unmount` subcommands
```

The mount depends only on `protondisk.core.ProtonDisk` and `fuse` (fusepy). Layering
invariant preserved: only `core/runner.py` touches the binary.

## 4. FUSE operations

`ProtonDiskFS(fuse.Operations)`:

| Op | Behavior |
| --- | --- |
| `getattr(path, fh=None)` | Resolve the entry (via cache, see §6) → stat dict: dirs `S_IFDIR\|0o555`, files `S_IFREG\|0o444`, `st_size`, `st_mtime`/`st_ctime`/`st_atime`, `st_nlink`. Missing path → `FuseOSError(ENOENT)`. |
| `readdir(path, fh)` | `core.list(proton_path)` (cached) → `['.', '..', *names]`. |
| `open(path, flags)` | If write access requested (`O_WRONLY`/`O_RDWR`/`O_APPEND`/etc.) → `FuseOSError(EROFS)`. Else **download-on-open** (§6) and return an integer file handle. |
| `read(path, size, offset, fh)` | Seek+read from the cached local copy for `fh`. |
| `release(path, fh)` | Close the handle and delete its temp copy. |
| `statfs(path)` | Static, plausible values (block size, etc.). |
| `write`, `create`, `mkdir`, `unlink`, `rmdir`, `rename`, `truncate`, `chmod`, `chown`, `symlink`, `link` | Raise `FuseOSError(EROFS)` — read-only. |

### Path mapping

`_proton_path(fuse_path) -> str`: mount root `"/"` → `"/my-files"`; `"/Reports/q3.pdf"` →
`"/my-files/Reports/q3.pdf"`. Pure function, unit-tested.

## 5. Read-only enforcement

All mutating ops raise `EROFS`; `open` rejects any write intent by inspecting `flags`
(`os.O_WRONLY`, `os.O_RDWR`; reject `O_APPEND`/`O_CREAT`/`O_TRUNC` too). FUSE is also
mounted with the kernel `ro` option as defense-in-depth. A pure helper
`_is_write_flags(flags) -> bool` is unit-tested.

## 6. Caching & download-on-open (fair-use critical)

Proton throttles heavy traffic, so the mount must not call the CLI once per `stat`.

- **Listing cache** (`cache.py`): `path -> (list[Entry], expires_at)` with a short TTL
  (default ~5 s, configurable). `readdir` populates it.
- **`getattr` served from the parent listing:** each `Entry` from `core.list` already
  carries `is_dir`, `size`, `mtime`. So `getattr("/A/b")` looks up `b` in the cached
  listing of `/A` — **an `ls` of N entries costs one `core.list`, not N `core.stat`s.**
  The mount root's own attributes are synthetic (a directory). Only a genuine cache miss
  (e.g. `stat` of a path whose parent isn't cached) falls back to `core.stat`.
- **Download-on-open:** `open` calls `core.download(proton_path, tmpdir)` into a
  per-handle temp directory; the local file is `tmpdir/basename`. `read` serves from it;
  `release` removes the temp dir. Whole-file download per open — honest limitation:
  the mount is convenience browsing + open/copy, not random-access streaming. (A future
  increment may add an open-file cache keyed by path+mtime.)
- **Single-threaded FUSE** (`nothreads=True`) this increment — no shared-cache locking
  needed; ample for browsing.

## 7. Lifecycle

- **`protondisk mount [MOUNTPOINT]`** (default `~/ProtonDisk`, created if absent):
  1. `core.auth_status()`; if logged out → clear error, exit non-zero.
  2. Mount **foreground** with `ro=True, nothreads=True, foreground=True`; print
     `Mounted /my-files at <mountpoint> — press Ctrl-C to unmount`.
  3. Ctrl-C / SIGINT → clean unmount.
- **`protondisk unmount [MOUNTPOINT]`** → `fusermount -u <mountpoint>` (fall back to
  `fusermount3 -u`).

## 8. Testing

- **Pure/unit-tested with a fake core (no kernel mount):** `_proton_path`,
  `_is_write_flags`, the TTL cache, the stat-dict builder (`_stat_dict(entry)`), and the
  `ProtonDiskFS` methods called directly — e.g. `fs.readdir("/", None)` returns names;
  `fs.getattr("/Reports")` returns a dir stat; `fs.getattr` of a file returns its size;
  `fs.open`+`fs.read` serve bytes from a fake `download`; mutating ops raise `EROFS`.
- **Live smoke test (controller):** actually mount against the real account, `ls` the
  mount, `cat` a file (compare to a direct `download`), then unmount — like the GUI live
  checks. Cleans up.

## 9. Dependencies

- **`fusepy`** — new, in the `[project.optional-dependencies] mount` extra (replaces the
  planned `pyfuse3`). Pure-Python.
- **libfuse2** — system package (already present). `install.sh` documents it
  (`apt install fuse` / `libfuse2`).

## 10. Versioning (project GIT rules)

Patch bump + push to `dev` per commit. Increment complete → **"Bump minor" → 0.5.0**
(CHANGELOG + README, merge `dev`→`main`, tag `v0.5.0`).

## 11. Scope guard (YAGNI)

This increment is **read-only** and **`/my-files` only**. Deferred: any writing
(create/write/mkdir/unlink/rename), other Drive sections (shared-with-me/trash/…),
background/daemonized mounting, an open-file content cache, and byte-range/random-access
optimization.

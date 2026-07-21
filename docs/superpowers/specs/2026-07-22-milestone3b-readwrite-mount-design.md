# ProtonDisk Milestone 3 — Read-write FUSE Mount + Progress Notifications (Design)

**Date:** 2026-07-22
**Status:** Approved (brainstorming complete)
**Scope:** Increment 2 of Milestone 3 — make the mount **read-write** (→ 0.6.0), and surface
transfer progress via **desktop notifications**. Builds directly on the read-only mount (0.5.0).

## 1. Summary

Extend `protondisk/mount/` so Proton Drive `/my-files` is mounted **read-write**: copy/paste
files in, save, make folders, delete, rename/move — all through any file manager. Because the
`proton-drive` CLI only does **whole-file** uploads, writes buffer to a local temp file and
upload on close (`release`). Transfer activity (download/decrypt/encrypt/upload) is surfaced
through **libnotify desktop notifications**, reusing the `--verbose` phase stream and
`parse_progress_line` built for the GUI.

## 2. Scope decision (user-confirmed)

**Copy-in + whole-file save.** Support: paste/drag files in, new files, save
(open→write→close re-uploads the whole file with `conflict=replace`), `mkdir`, delete→`trash`,
and rename/move to a **non-colliding** name. Deliberately **not** supported: renaming onto an
*existing* name (some editors' safe-save dance) — Proton's rename refuses to overwrite
(*"a file with this name already exists"*), so that case returns `EEXIST`.

The Drive currently holds only disposable test data (user confirmed), so development can test
writes freely against the live account; the code is still built to production quality.

## 3. Feasibility (captured)

- `upload -c replace <local> <parent>` cleanly **overwrites** an existing name → one file, new
  revision (verified). This is the save/copy-in mechanic.
- `rename` onto an existing name **fails** (verified) → we return `EEXIST` for that case.
- **libnotify** available three ways on this machine: `notify-send`, `gi` `Notify` (GObject
  introspection), and the freedesktop Notifications D-Bus service (registered). We use `gi`
  `Notify` for in-place updates, degrading to a silent no-op if unavailable.

## 4. Write model — buffer locally, upload on close

Per open **write handle**, a temp dir holds one buffer file:

| FUSE op | Behavior |
| --- | --- |
| `create(path, mode, fi=None)` | new empty buffer file; register a WRITE handle (dirty=False→True on first write); return fh. No upload yet. |
| `open(path, flags)` | read intent → existing download-on-open (unchanged). Write intent on an **existing** file → download it into the buffer first (partial edits keep unmodified bytes); register a WRITE handle. Write intent on a missing file → behave like `create`. |
| `write(path, data, offset, fh)` | seek+write into the buffer; mark dirty; return `len(data)`. |
| `truncate(path, length, fh=None)` | truncate the buffer to `length` (open the buffer if `fh` is None: download-then-truncate for an existing file). |
| `flush(path, fh)` | if the handle is dirty, upload now and clear dirty (covers apps that `fsync`/`close` semantics via flush). |
| `release(path, fh)` | if still dirty, upload; then close + remove the temp dir; drop the handle. |
| `fsync(path, datasync, fh)` | same as `flush`. |

**Upload:** `core.upload(buffer_path_renamed_to_basename, parent, conflict="replace",
progress=cb)`. The buffer file must carry the **target basename** so the CLI uploads it under
the right name — the write handle's temp dir contains a file named exactly `basename(path)`.

**getattr for in-progress files:** if a WRITE handle is open for `path`, report the buffer
file's live `st_size`/`st_mtime` (so the copying app sees its bytes land); else the existing
cached-listing path. A newly `create`d file not yet in the listing is also resolved from its
open handle.

## 5. Directory & namespace ops

| FUSE op | Core call | After |
| --- | --- | --- |
| `mkdir(path, mode)` | `core.mkdir(path)` | invalidate parent listing |
| `unlink(path)` / `rmdir(path)` | `core.trash(path)` | invalidate parent listing |
| `rename(old, new)` | same parent → `core.rename(old, basename(new))`; different parent → `core.move(old, parent(new))` then `core.rename` if the basename differs. If `new` already exists in its dir → `FuseOSError(EEXIST)`. | invalidate both parents |

All raise `FuseOSError(EIO)` on a `ProtonDiskError` (consistent with the read path).

## 6. Cache invalidation

Every mutation invalidates the affected directory listing(s) in the `ListingCache`, so new /
changed / removed entries appear immediately. `create` also seeds the parent as needing a
refresh. Uploads-on-release invalidate the parent.

## 7. Mount flags & threading

- Drop `ro=True`; mount **read-write**. Per-file access is still governed by `open`.
- Keep **`nothreads=True`**: write buffers are per-handle and mutations are synchronous; a
  single-threaded loop avoids buffer/cache locking. (The upload in `release` blocks that one
  op — acceptable and expected.)

## 8. Progress notifications

New `protondisk/mount/notify.py` — a best-effort `Notifier`:

- On init: try `import gi; gi.require_version("Notify","0.7"); Notify.init("ProtonDisk")`. On
  any failure → `self._enabled = False` and every method is a silent no-op (headless/cron safe).
- `begin(key, summary, body) -> handle`: create + show a `Notify.Notification`, return it (or None).
- `update(handle, body)`: set body + `show()` again — updates the **same** popup in place.
- `finish(handle, body, timeout_ms=3000)`: final update with a short expire timeout.

Wiring in `fs.py`:
- **Download-on-open** (read): switch `core.download(...)` → `core.download(..., progress=cb)`;
  `cb` updates a "Opening <name>" notification through `Downloading… / Decrypting… / Verifying…`,
  then `finish` "Ready".
- **Upload-on-release** (write): `core.upload(..., conflict="replace", progress=cb)`; `cb`
  updates a "Saving <name>" notification through `Encrypting… / Uploading… / Finishing…`, then
  `finish` "Saved to Proton Drive".
- Notifications fire **only** for content transfers (open/read download, release upload), never
  for `getattr`/`readdir`. One notification per transfer, updated in place.
- The `Notifier` is injected into `ProtonDiskFS(disk, ttl=..., notifier=...)` so tests pass a
  fake and assert phase text without touching D-Bus.

Honest limitation surfaced to the user in README: during the upload the file manager's own copy
dialog may sit at "finishing"; the ProtonDisk notification is the live status.

## 9. Testing

- **Unit (fake core + fake notifier, no kernel mount):** `create`→`write`→`release` uploads the
  buffer with `conflict="replace"` under the right basename; `getattr` of a path with an open
  write handle reports the buffer size; `write`/`truncate` update the buffer; `mkdir`/`unlink`/
  `rmdir` call `core.mkdir`/`core.trash`; `rename` maps same-dir→`rename`, cross-dir→`move`(+rename),
  target-exists→`EEXIST`; a `ProtonDiskError` → `EIO`; the notifier receives `begin`/`update`
  (phase)/`finish` for a transfer and nothing for a `readdir`; read path still works.
- **Live (controller):** mount read-write against the real account; `cp` a file in (and via
  Nautilus paste), `mkdir`, `rm`, `rename`, edit-and-save a text file; verify each on the Drive
  and that a notification appeared; unmount. Test files are disposable.

## 10. Versioning

Patch bump + push per commit. Increment done → **"Bump minor" → 0.6.0** (CHANGELOG + README,
merge `dev`→`main`, tag `v0.6.0`).

## 11. Scope guard (YAGNI)

Deferred: rename-over-existing / full editor safe-save; delta/partial uploads (every save
re-uploads the whole file); an open-file write-back cache across handles; byte-range random
writes without a full local buffer; notification action buttons; per-transfer progress *bars*
(we show phase text, since GNOME doesn't render notification progress values reliably).

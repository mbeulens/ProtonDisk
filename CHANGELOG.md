# Changelog

All notable changes to ProtonDisk are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project follows a
patch-per-commit scheme (the `VERSION` file is the single source of truth).

> Note: version numbers with a `13` segment (e.g. `0.1.13`) are deliberately
> skipped — "To be sure to be sure!"

## [2.0.0] — 2026-07-22

**Editors just work on the mount.** This release makes real text editors and file
managers behave correctly on a mounted Proton Drive — the save patterns that broke in
1.0.0 now work, and editor scratch files no longer clutter your Drive.

### Added
- **Editor & OS temp files are kept local-only.** vim/emacs swap and lock files, GNOME
  atomic-save temps (`.goutputstream-*`), LibreOffice/Office locks, `.DS_Store`,
  `Thumbs.db`, and similar now live in a local scratch area and are **never uploaded** to
  Proton Drive — no upload churn, no clutter, and no stranded lock files if an editor or
  the network drops. They still work fully within the mount (create/read/write/delete/list).
  Backups (`file~`) and generic `*.tmp` stay synced.

### Fixed
- **Atomic-rename saves work** (GNOME Text Editor, VS Code). Replacing an existing file by
  renaming a temp over it now succeeds — the old file is moved to Proton trash
  (recoverable) and the new content takes its place. A GNOME `.goutputstream-*` save
  uploads its content straight to the destination with nothing extra left behind.
- **Delete-then-recreate no longer ghosts.** Proton is eventually consistent, so a
  just-deleted name used to linger in listings and make an `O_EXCL` create fail with
  "File exists" (breaking nano/vim swap files, `rm x; touch x`). Deleted names are now
  tombstoned briefly so they read as gone until the Drive catches up.

### Compatibility
- No changes to the CLI, the GUI, or the on-disk format. The mount's behavior for editor
  temp files changed (they no longer appear on the Drive) — intentional, and the reason
  for the major version bump.

## [1.0.0] — 2026-07-22

**First stable release.** ProtonDisk is now a complete Linux app for Proton Drive: a
graphical browser, a real mountable disk, and a one-command install that sets it up to
run automatically — all built on the official `proton-drive` CLI, so authentication and
end-to-end encryption stay with Proton.

### The product at 1.0
- **Core** (`protondisk.core`) — a typed Python wrapper over `proton-drive`: auth, browse,
  transfer, organize, sharing, with a clean error model.
- **GUI** (GTK4 + libadwaita) — sign in, browse `My files`, upload/download with live
  transfer progress, new folder, rename, move, trash, and a sharing dialog.
- **Mount** — Proton Drive as a **read-write disk** in any file manager: copy/paste files
  in, save, make folders, delete, rename/move, with desktop notifications for transfer
  phases.
- **Install** — `install.sh` wires the checkout for your user (venv, `protondisk` command,
  GUI entry) and a systemd user service that **auto-mounts `~/ProtonDisk` at login**.

### Added since 0.5.0
- **One-command install/uninstall** (`install.sh` / `uninstall.sh`): a `protondisk` command
  on PATH, the GUI application entry, and a systemd user service for auto-mount at login.
- **Auto-recovering mount** — a supervisor waits for the network **event-driven** (asleep on
  a NetworkManager signal, ~0% CPU) and remounts by itself when connectivity returns. It
  does **not** poll while offline.

### Fixed since 0.5.0
- **Offline never hangs the mount.** Metadata operations have a bounded (120 s) timeout, so
  an unreachable network fails cleanly with an I/O error in a few seconds instead of ever
  blocking; large uploads/downloads opt out so they can still run long.

### Known limitations
- Renaming onto an existing name returns `EEXIST` (Proton's rename cannot overwrite), so some
  editors' safe-save (write-temp-then-rename) may fail — save whole-file instead.
- Every save re-uploads the whole file (no deltas).
- Auto-mount needs a valid Proton session; if it expires, `protondisk auth login` then
  `systemctl --user restart protondisk-mount.service`.

### Not in 1.0 (planned)
- Photos and albums, public share links, and multi-account — the same features the official
  CLI defers.

## [0.5.0] — 2026-07-22

Milestone 3: **Proton Drive as a mountable disk** — a read-write FUSE mount with desktop
notifications. `protondisk mount [MOUNTPOINT]` / `protondisk unmount [MOUNTPOINT]`; default
mount point `~/ProtonDisk`, root maps to `/my-files`. Built on `protondisk.core` via fusepy.

### Added
- **Browse Proton Drive as a disk** in any file manager or the shell — folders, sizes, and
  timestamps, with files read via download-on-open (cached). A short-TTL listing cache
  serves `getattr` from the parent listing, so an `ls` of N files is one Drive call.
- **Read-write** — copy/paste files in (upload), save edits, create folders, delete
  (→ trash, recoverable), and rename/move. Writes buffer to a local temp file and upload
  (whole-file, `conflict=replace`) on close; namespace ops map to the core façade.
- **Desktop notifications** (libnotify, best-effort) surface the live transfer phase —
  Downloading / Decrypting / Encrypting / Uploading / Finishing — reusing the CLI's
  `--verbose` stream. Silently disabled where libnotify/D-Bus is unavailable.
- Core: `CLIRunner.run_streaming` + `parse_progress_line` drive transfer progress;
  `upload`/`download` accept a `progress=` callback.

### Fixed
- **File sizes are now the true plaintext size.** Previously the encrypted storage size
  (`totalStorageSize`) was reported — e.g. a small text file showed as tens of bytes. Now
  uses `claimedSize`, which also corrects the sizes shown in the GUI. (Before the fix this
  also corrupted appends by positioning writes past the real end of file.)
- The read-write mount advertises writable permissions (0755/0644) so file managers offer
  paste/save/delete.
- `touch` / copying an empty file / saving a 0-byte file now persists (previously dropped).

### Known limitations
- Renaming onto an existing name returns `EEXIST` (Proton's rename cannot overwrite), so
  some editors' safe-save (write-temp-then-rename) may fail — save whole-file instead.
- Every save re-uploads the whole file (no deltas).
- During an upload the file manager's own copy dialog may sit at "finishing"; the ProtonDisk
  notification shows the real status.
- The mount needs system **fusepy** + **libfuse2**; run it from a `--system-site-packages`
  venv (the same `.venv-gui` used for the GUI). Read-only-first was an internal step; this
  release ships the full read-write mount.

## [0.4.0] — 2026-07-20

GUI increment 2: **file management and sharing** in the graphical browser.

### Added
- **New Folder** — a header button with a validated name dialog.
- **Row context menu** (right-click) with Rename / Move / Trash / Share, targeting the
  exact row under the pointer.
- **Rename** — inline name dialog.
- **Move** — cut an item, navigate to a destination folder, and Paste (guards against
  moving a folder into itself or its own parent).
- **Trash** — with a destructive confirmation dialog.
- **Share** — a dialog showing the current sharing status plus invite by email and role
  (viewer / editor / admin).

### Fixed
- Right-click now acts on the exact row under the pointer (previously a fragile
  row-height estimate could target the wrong file when the list was scrolled).
- Paste captures its destination at click time, so navigating during an in-flight move
  can no longer move the item to the wrong folder.
- File-dialog errors are surfaced (previously any dialog error was treated as a cancel);
  uploads refresh once after the last file; a skipped upload toasts honestly; a signed-in
  user with an empty folder no longer falls back to the sign-in screen on an error.

### Notes
- Sharing shows status and sends invites; the `sharing status` JSON shape for an
  already-shared node is still a best-effort parse pending a live capture.
- Drag-and-drop, grid view, thumbnails, and public share links remain out of scope.

## [0.3.0] — 2026-07-20

Second milestone (first increment): **the GTK4 + libadwaita graphical browser**,
`protondisk gui`. Built entirely on `protondisk.core`; every network call runs off
the UI thread so the window never freezes.

### Added
- **`protondisk/gui/` — a GTK4/libadwaita desktop app** launched with `protondisk gui`:
  - Sign-in gating (a "Sign in with Proton" screen when logged out; the account
    email is shown in the header).
  - **Browse & navigate** `My files`: a list view with folder/file icons and
    human-readable sizes, a clickable breadcrumb, Back/Forward history, and Refresh.
  - **Upload & download** via labeled toolbar buttons and native file pickers,
    with completion toasts.
  - **Live transfer progress** in the status bar: a throbber plus the current phase
    (Starting / Encrypting / Uploading / Downloading / Verifying / Decrypting /
    Finishing), parsed from the CLI's `--verbose` stream.
  - Error dialogs on failure; the view always recovers (never a stuck spinner).
- **Core additions supporting the GUI:**
  - `CLIRunner.run_streaming` — reads the CLI's output line-by-line so transfer
    progress can be surfaced as it happens.
  - `parse_progress_line` — maps `--verbose` log lines to short phase labels.
  - `upload`/`download` accept an optional `progress=` callback.
- **Launcher & icon:** `scripts/protondisk-gui` (self-healing GTK venv, always runs
  the latest source) and `assets/protondisk.svg`, for a desktop `.desktop` entry.

### Notes
- The GUI needs system PyGObject/GTK4/libadwaita. Use a `--system-site-packages`
  virtualenv (see README); tests run under it.
- Organize (rename/move/trash) and sharing are not yet in the GUI — next increment.

## [0.2.0] — 2026-07-20

First functional milestone: **the core CLI wrapper** (`protondisk.core`) — the
shared foundation that the upcoming GTK4 GUI and FUSE mount will both build on.

### Added
- **`protondisk.core` package** — a typed Python wrapper around the official
  `proton-drive` CLI (`cli-drive@0.5.0`). All communication with Proton Drive
  goes through the official, end-to-end-encrypted binary; ProtonDisk never
  handles credentials or crypto itself.
- **`CLIRunner`** (`core/runner.py`) — the single point that invokes the
  `proton-drive` binary. Runs commands with `--json`, parses stdout (handling
  the CLI's `undefined`/empty output), and maps failures to a typed exception
  hierarchy. Discovers the binary on `PATH` and raises a clear
  `CLINotFoundError` if it is missing.
- **Typed models** (`core/models.py`) — `Entry`, `AuthStatus`, `TransferResult`,
  `ShareInfo`, parsed from real captured `proton-drive` JSON (Result-wrapped
  names, ISO-8601 timestamps, `uid`, `totalStorageSize`).
- **`ProtonDisk` façade** (`core/client.py`) — typed methods:
  - Auth: `auth_status()` (probe-based, since the CLI has no `auth status`),
    `login()`, `logout()`.
  - Browse: `list(path)`, `stat(path)`.
  - Transfer: `upload(local, parent, conflict=...)`, `download(remote, folder)`.
  - Organize: `mkdir(path)`, `rename(path, new_name)`, `move(src, target_parent)`,
    `trash(path)`.
  - Sharing: `sharing_status(path)`, `sharing_invite(path, user, role, message)`.
- **Exception hierarchy** (`core/errors.py`): `ProtonDiskError` →
  `CLINotFoundError`, `AuthError`, `NotFoundError`, `ConflictError`,
  `RateLimitError` (Proton fair-use throttling).
- **`protondisk` CLI** (`cli.py`) — a thin entrypoint exercising the core:
  `protondisk version`, `protondisk auth-status`, `protondisk ls PATH`.
- **Tooling** — `pyproject.toml` (version read dynamically from `VERSION`),
  `scripts/bump-patch.sh` (patch bump that skips `13`), and a 53-test suite that
  fakes the CLI boundary (no Proton account required to run).

### Known limitations / deferred
- Interactive `auth login` is not yet exercised against the live CLI (its
  subprocess handling — `--json`, captured output, timeouts — will be reconciled
  in the GUI/live milestone).
- The `sharing status` JSON shape for a *shared* node is not yet captured;
  `ShareInfo`'s shared-branch parsing is a best-effort placeholder.
- Photos/albums, public share links, and multi-account are out of scope for v1.

## [0.1.x] — 2026-07-20

Project bootstrap: design document, Milestone 1 implementation plan (both
reconciled against the real `proton-drive` CLI), repository scaffolding, and the
incremental TDD build of the core package.

[0.2.0]: https://github.com/mbeulens/ProtonDisk/tree/v0.2.0

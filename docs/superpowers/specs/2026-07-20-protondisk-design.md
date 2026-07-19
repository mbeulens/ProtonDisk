# ProtonDisk — Design Document

**Date:** 2026-07-20
**Status:** Approved (brainstorming complete)
**Repo:** [mbeulens/ProtonDisk](https://github.com/mbeulens/ProtonDisk) (public)

## 1. Summary

ProtonDisk makes [Proton Drive](https://proton.me/drive) usable as a local disk and
through a graphical file browser on Linux. It is built **on top of the official
`proton-drive` CLI**, which handles authentication and end-to-end encryption. ProtonDisk
never talks to Proton's API or crypto directly — the official binary is the trusted engine.

The name is deliberately **"Disk", not "Drive"**, to avoid confusion with the official
Proton Drive product. ProtonDisk is a third-party convenience layer sitting on top of it.

Two headline capabilities:

1. **Mount** — Proton Drive appears as a real mounted folder (FUSE) that any file manager
   or terminal can browse.
2. **GUI** — a Nautilus/Explorer-style graphical file browser (GTK4 + libadwaita).

## 2. Context & Motivation

- The official `proton-drive` CLI (TypeScript/Bun, built on the Proton Drive SDK) provides
  one-shot commands: `auth`, `filesystem list/upload/download`, `sharing`, trash, invites.
  It has **no built-in mount and no background sync** — only the full Proton apps do.
- There is **no official Python SDK**. Reimplementing Proton's SRP auth + PGP crypto in
  Python would be large, security-sensitive, and brittle.
- Prior attempts to use rsync/rclone-style syncing did not work well for the user; Proton's
  own CLI exists precisely because generic sync tools were inadequate.
- Therefore ProtonDisk **wraps the official CLI** and adds the two things it lacks: a
  mountable disk and a graphical browser.

## 3. Architecture

Three layers over one shared engine. Dependencies flow one direction: GUI and mount both
depend on the core; the core is the only code that touches the `proton-drive` binary.

```
┌──────────────────┐     ┌──────────────────┐
│   GUI (GTK4)     │     │   FUSE mount     │   Milestones 2 & 3
│  Nautilus-style  │     │  Drive as a disk │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └───────────┬────────────┘
                     ▼
         ┌───────────────────────┐
         │   protondisk core     │   Milestone 1 (foundation)
         │  Python wrapper around │
         │   `proton-drive` CLI   │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │  official proton-drive │   (auth + E2E encryption)
         │   binary  (--json)     │
         └───────────────────────┘
```

**Key principle:** the core layer is the *only* thing that knows about the `proton-drive`
binary. GUI and mount call typed Python methods, never shell out directly. The CLI
dependency lives in one swappable place.

### Tech stack

- **Python 3.12+**
- **GUI:** GTK4 + libadwaita via PyGObject (`gi`) — the same stack modern GNOME Files uses,
  giving the most native Nautilus/Explorer look and built-in sidebar/header-bar/list-grid widgets.
- **Mount:** `pyfuse3` (async, actively maintained).
- **Backend:** `subprocess` calls to `proton-drive … --json`.
- **Platform:** Linux only (for now).
- **Secrets:** none stored by ProtonDisk. The official CLI owns the session store
  (libsecret on Linux). ProtonDisk only checks/triggers auth.

## 4. Milestone 1 — Core Layer (the foundation)

Python package `protondisk/core/` exposing one clean, typed API consumed by GUI and mount.

### Public API (sketch)

```python
class ProtonDisk:
    # auth
    def auth_status() -> AuthStatus        # logged in? which account?
    def login() -> None                    # triggers browser login via CLI
    def logout() -> None

    # browsing
    def list(path: str) -> list[Entry]     # Entry: name, path, is_dir, size, mtime, id
    def stat(path: str) -> Entry

    # transfer
    def upload(local: str, remote: str, *, conflict="skip") -> TransferResult
    def download(remote: str, local: str) -> TransferResult

    # organize
    def mkdir(path: str) -> None
    def move(src: str, dst: str) -> None
    def trash(path: str) -> None

    # sharing (not a filesystem op)
    def sharing_status(path: str) -> ShareInfo
    def sharing_invite(path: str, user: str, role="editor", message="") -> None
```

### Internals

- A single `_run(*args)` helper invokes `proton-drive … --json`, capturing stdout, stderr,
  and exit code.
- Typed dataclasses (`Entry`, `AuthStatus`, `TransferResult`, `ShareInfo`) parse the JSON.
  GUI/mount never see raw JSON.
- **CLI discovery:** locate `proton-drive` on `PATH` or a configured path; raise a clear
  `CLINotFoundError` with install guidance if missing.

### Error model

One exception hierarchy so all callers handle failures uniformly:

```
ProtonDiskError
├── AuthError          # not logged in / session expired
├── NotFoundError      # path does not exist
├── ConflictError      # upload conflict, name collision
├── RateLimitError     # Proton fair-use throttling
└── CLINotFoundError   # proton-drive binary missing
```

CLI exit codes and JSON error fields map to these exceptions.

### Testing (TDD-friendly)

- The core only shells out; it never touches the network directly. Tests **fake the
  subprocess boundary**: feed canned `--json` fixtures (captured from real `proton-drive`
  output) and assert parsed dataclasses + error mapping. Fast, deterministic, no account
  needed in CI.
- A small set of **optional live integration tests** (skipped unless a real session exists)
  validate against the actual binary.

## 5. Milestone 2 — GUI

GTK4 + libadwaita desktop app, `protondisk/gui/`, that only calls the core API.

### Layout

```
┌─────────────────────────────────────────────┐
│ ⌂  ← →  /my-files/Reports          ⚙  [⇅]   │  Adw.HeaderBar: nav, breadcrumb, menu
├───────────┬─────────────────────────────────┤
│ Sidebar   │  📁 Reports    📁 Photos         │
│  ⌂ My files│  📄 q3.pdf     📄 notes.txt      │  icon/list view of current folder
│  🗑 Trash  │  📄 budget.xlsx                  │
│  🔗 Shared │                                 │
└───────────┴─────────────────────────────────┘
   status bar: "12 items · logged in as user@pm.me"
```

### Interactions

- **Browse:** click folders → `core.list(path)`; breadcrumb + back/forward history.
- **Transfer:** drag-and-drop or buttons → `core.upload/download`; a progress area for transfers.
- **Organize:** right-click context menu → new folder, rename (move), move to trash.
- **Share:** right-click → "Share…" dialog → `core.sharing_status` / `core.sharing_invite`.
- **Auth:** on launch `core.auth_status()`; if logged out, a "Sign in" screen calls
  `core.login()` (browser flow).

### Threading

Every core call blocks on the network via the CLI. The GUI runs core calls on a **worker
thread** and marshals results back to the GTK main loop with `GLib.idle_add`, so the UI never
freezes. A simple in-memory **directory cache** (with manual refresh) avoids re-hitting the
CLI on every navigation and respects Proton's fair-use guidance.

### Testing

GUI logic (state, path history, cache) is unit-tested with a **mocked core**. GTK widget
clicks are not automated — tests stay at the logic boundary.

## 6. Milestone 3 — FUSE Mount (the "disk")

`protondisk/mount/` — Proton Drive as a real mounted folder (e.g. `~/ProtonDisk/`) that any
file manager or terminal can browse. Built on `pyfuse3`, calling only the core API.

### FUSE op → core mapping

| Filesystem operation      | Core call                               |
| ------------------------- | --------------------------------------- |
| `readdir` (list a folder) | `core.list(path)`                       |
| `getattr` (stat a file)   | `core.stat(path)`                       |
| `read` (open + read)      | `core.download(path, tmp)`, serve bytes |
| `write` / `create`        | buffer locally → `core.upload` on flush |
| `mkdir`                   | `core.mkdir(path)`                      |
| `rename`                  | `core.move(src, dst)`                   |
| `unlink` / `rmdir`        | `core.trash(path)`                      |

### Hard parts and how we handle them

- **Latency & fair-use:** a naïve mount would call the CLI on every `stat`/`ls` — slow, and
  would trip Proton's throttling. The mount keeps a short-lived **metadata cache**
  (attributes + directory listings, small TTL).
- **Whole-file transfers:** the CLI moves whole files, not byte ranges. `read` downloads the
  file once to a local temp cache and serves from it; `write` buffers locally and uploads on
  close. **ProtonDisk's mount is convenience browsing + open/save, not a high-performance
  random-access filesystem.** Only the full Proton apps have a real sync engine; ProtonDisk
  does not pretend to be one.
- **Sharing:** not representable as files — stays a GUI/CLI feature, absent from the mount.
  No fake `.share` files.
- **Mount lifecycle:** `protondisk mount ~/ProtonDisk` / `protondisk unmount`; clean unmount
  on Ctrl-C / signal; refuses to mount if not authenticated.

### Testing

The FUSE-op-to-core translation layer is unit-tested with a **mocked core** (e.g. assert
`read` triggers exactly one `download`, cache prevents a second call). Optional live smoke
test mounts against a real session.

## 7. Repository Layout

```
ProtonDisk/
├── protondisk/
│   ├── core/          # Milestone 1 — CLI wrapper, dataclasses, errors
│   ├── gui/           # Milestone 2 — GTK4 app
│   ├── mount/         # Milestone 3 — pyfuse3 layer
│   └── cli.py         # `protondisk` entrypoint (launch gui / mount / unmount)
├── tests/             # fixtures/ (canned --json), unit tests per layer
├── docs/
│   └── superpowers/specs/   # this design doc
├── pyproject.toml     # deps + entrypoint
├── install.sh
├── README.md
├── CHANGELOG.md
└── .gitignore
```

## 8. Configuration

`~/.config/protondisk/config.toml`:

- Path to the `proton-drive` binary (if not on `PATH`).
- Default mount point.
- Cache TTLs.

**No secrets stored** — Proton owns the session store.

## 9. Dependencies

- `PyGObject` (GTK4 + libadwaita) — GUI.
- `pyfuse3` — mount.
- Standard library for the rest (`subprocess`, `json`, `dataclasses`, `tomllib`).
- GTK4/libadwaita and FUSE come from system packages; `install.sh` documents the `apt`
  prerequisites.

## 10. Versioning (per project GIT rules)

- Every file change → patch bump + commit + push to `dev` (0.1.0 → 0.1.1 → …).
- **Milestone 1 (core) done → "Bump minor"** → CHANGELOG + README, merge `dev`→`main` → **0.2.0**.
- **Milestone 2 (GUI) done → "Bump minor"** → **0.3.0**.
- **Milestone 3 (mount) done → "Bump minor"** → **0.4.0**.
- First fully working end-to-end release → **"Bump major" → 1.0.0**.
- Any version with a `13` segment (e.g. 0.13.0) is **skipped** with the commit message
  `"To be sure to be sure!"`.

## 11. Scope Guard (YAGNI)

v1 deliberately **excludes** (matching the official CLI's own "what comes next" list):

- Photos and albums.
- Files/folders shared via secure public link.
- Multi-account support.

These can be added later as minor bumps once the three core milestones are solid.

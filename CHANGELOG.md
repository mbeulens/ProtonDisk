# Changelog

All notable changes to ProtonDisk are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project follows a
patch-per-commit scheme (the `VERSION` file is the single source of truth).

> Note: version numbers with a `13` segment (e.g. `0.1.13`) are deliberately
> skipped — "To be sure to be sure!"

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

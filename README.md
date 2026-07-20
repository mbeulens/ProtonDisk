# ProtonDisk

**Use [Proton Drive](https://proton.me/drive) as a mounted disk and a graphical
file browser on Linux.**

ProtonDisk is a third-party convenience layer built **on top of the official
[`proton-drive` CLI](https://proton.me/blog/proton-drive-cli)**, which handles
authentication and end-to-end encryption. ProtonDisk never touches your Proton
credentials or crypto — it drives the official binary and adds the two things it
lacks: a **mountable disk** and a **graphical browser**.

> It's called "Disk" (not "Drive") to avoid confusion with the official Proton
> Drive product.

## Status

| Milestone | Feature | State |
|-----------|---------|-------|
| **1** | **Core CLI wrapper** (`protondisk.core`) | ✅ **Done — v0.2.0** |
| **2** | **GTK4 + libadwaita graphical browser** (browse, transfer, organize, sharing) | ✅ **Done — v0.4.0** |
| 3 | FUSE mount (Proton Drive as a disk) | ⏳ Planned |

## Architecture

```
┌──────────────────┐     ┌──────────────────┐
│   GUI (GTK4)     │     │   FUSE mount     │   Milestones 2 & 3
└────────┬─────────┘     └────────┬─────────┘
         └───────────┬────────────┘
                     ▼
         ┌───────────────────────┐
         │   protondisk.core     │   Milestone 1 ✅
         │  (typed CLI wrapper)  │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │  proton-drive binary  │   (auth + E2E encryption)
         └───────────────────────┘
```

Only `protondisk/core/runner.py` ever invokes the `proton-drive` binary; the GUI
and mount will consume the typed `ProtonDisk` façade, never the CLI directly.

## Requirements

- **Linux**, **Python 3.12+**
- The official **`proton-drive` CLI** on your `PATH`
  ([download](https://proton.me/blog/proton-drive-cli) or build from source).
  Sign in once with `proton-drive auth login` (browser flow).

## Install (from source)

```bash
git clone https://github.com/mbeulens/ProtonDisk.git
cd ProtonDisk
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

## Usage (core CLI, Milestone 1)

```bash
# Show the ProtonDisk version
protondisk version

# Are you logged in? (probes the proton-drive session)
protondisk auth-status

# List a Drive folder
protondisk ls /my-files
```

If the `proton-drive` binary isn't found, ProtonDisk reports a clear error rather
than a traceback.

## Graphical browser (Milestone 2)

The GUI needs **system** PyGObject/GTK4/libadwaita (not pip-installable in a plain
venv), so it runs from a `--system-site-packages` virtualenv:

```bash
python3 -m venv --system-site-packages .venv-gui
.venv-gui/bin/pip install -e '.[dev]'
.venv-gui/bin/python -m protondisk.cli gui
```

Or just run the launcher (creates the venv on first run, always launches the
latest source):

```bash
scripts/protondisk-gui
```

You can also install a desktop entry pointing `Exec=` at `scripts/protondisk-gui`
and `Icon=` at `assets/protondisk.svg`.

The window signs you in, browses **My files** (list view, breadcrumb,
back/forward, refresh), and uploads/downloads files. The status bar shows a
throbber and the live transfer phase (Encrypting / Uploading / Downloading /
Decrypting / Finishing). Right-click a row to **rename, move (cut → Paste),
trash, or share** it, and use **New Folder** in the header. Run GUI tests with
`.venv-gui/bin/pytest`.

## Using the core from Python

```python
from protondisk.core import ProtonDisk, AuthError

disk = ProtonDisk()                    # finds `proton-drive` on PATH
status = disk.auth_status()
if not status.logged_in:
    disk.login()                       # opens the browser sign-in

for entry in disk.list("/my-files"):
    kind = "dir " if entry.is_dir else "file"
    print(kind, entry.name, entry.size)

disk.upload("./report.pdf", "/my-files/Reports", conflict="skip")
disk.download("/my-files/Reports", "./backups")
disk.sharing_invite("/my-files/Reports", "colleague@pm.me", role="editor")
```

All failures raise a typed subclass of `ProtonDiskError`
(`CLINotFoundError`, `AuthError`, `NotFoundError`, `ConflictError`,
`RateLimitError`).

## Development

```bash
.venv/bin/pytest          # run the test suite (fakes the CLI boundary; no account needed)
```

The `VERSION` file is the single source of truth; each change bumps the patch via
`scripts/bump-patch.sh`. See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

TBD.

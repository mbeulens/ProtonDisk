# ProtonDisk Milestone 2 (first increment) — GTK4 GUI: Browse + Transfer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GTK4 + libadwaita desktop app (`protondisk gui`) that signs in, browses/navigates Proton Drive folders, and uploads/downloads files — built entirely on the `protondisk.core` façade from Milestone 1.

**Architecture:** `protondisk/gui/`. The GUI **only** calls `protondisk.core.ProtonDisk`; it never invokes the `proton-drive` binary directly. Every core call (which blocks on the network) runs on a **worker thread** and marshals its result back to the GTK main loop via `GLib.idle_add`, so the UI never freezes. **Pure logic** (navigation history, breadcrumb, directory cache) lives in **gi-free modules** that unit-test without a display; **GTK widgets** live in separate modules verified by actually launching the app.

**Tech Stack:** Python 3.12+, PyGObject (system package), GTK 4, libadwaita (Adw 1), `pytest`. Runs under a `--system-site-packages` venv (`.venv-gui`) so system PyGObject is importable alongside pip's pytest and the editable `protondisk`.

**This increment delivers (→ 0.3.0):** login gating, folder browse/navigate (list view, breadcrumb, back/forward), upload, download. **Deferred to a later GUI increment:** rename/move/trash, sharing dialog, drag-and-drop, grid view, thumbnails.

## Global Constraints

- **Environment:** all GUI code and tests run under **`.venv-gui`** (created with `python3 -m venv --system-site-packages .venv-gui`, then `.venv-gui/bin/pip install pytest -e .`). Run tests with **`.venv-gui/bin/pytest`**. A DISPLAY is available (`DISPLAY=:1`, X11) for launch verification.
- **Layering:** `protondisk/gui/*` may import `protondisk.core` only — never `subprocess` and never the `proton-drive` binary. The core stays the single dependency point.
- **gi-free logic:** `protondisk/gui/navigation.py` (and any pure-logic module) MUST NOT `import gi`. Widget modules (`app.py`, `window.py`) may.
- **Threading:** no core call may run on the GTK main thread. Use the Task-3 worker for every core call; deliver results/errors via `GLib.idle_add`.
- **Versioning (project GIT rules):** the `VERSION` file is the single source of truth. Every task commit runs **`scripts/bump-patch.sh`** (increments patch, skips patch 13 with a stderr notice → use commit message `To be sure to be sure!` if it fires), then `git push origin dev`. Versions are computed from `VERSION` at execution time (never hardcoded), so they cannot collide with doc commits. Milestone increment done → **"Bump minor" → 0.3.0**.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'`; end messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **GENUINE verification:** actually run every test and launch command; paste REAL output. Fabricated transcripts are unacceptable.

---

## File Structure

```
protondisk/gui/
├── __init__.py
├── worker.py         # run_async(): core call on a thread -> GLib.idle_add callback
├── navigation.py     # NavigationState: path, back/forward history, dir cache (gi-free)
├── window.py         # Adw.ApplicationWindow: header/breadcrumb/list view + wiring
└── app.py            # Adw.Application + run(); launched by `protondisk gui`
tests/gui/
├── test_navigation.py    # pure logic, mocked core, gi-free
└── test_worker.py        # worker marshaling, runs a short GLib.MainLoop
protondisk/cli.py     # + `gui` subcommand (modify)
```

Verification helper used by widget tasks (run under `.venv-gui`, on `DISPLAY=:1`):
`scripts/gui-smoke.py` (created in Task 1) launches the app, lets it settle, saves a
PNG screenshot via the GdkPixbuf of the top window, and quits — proving the app renders
without error. Live tasks additionally rely on the logged-in `proton-drive` session.

---

### Task 1: GUI environment, package skeleton, launchable window, `protondisk gui`

**Files:**
- Create: `protondisk/gui/__init__.py`, `protondisk/gui/app.py`, `protondisk/gui/window.py`, `scripts/gui-smoke.py`
- Modify: `protondisk/cli.py` (add `gui` subcommand)
- Test: `tests/gui/test_window_builds.py`

**Interfaces:**
- Produces:
  - `protondisk.gui.window.MainWindow(Adw.ApplicationWindow)` — constructor `MainWindow(application, disk)` builds a header bar (title "ProtonDisk") and an empty content area (`Adw.ToolbarView` + a `Gtk.Box` placeholder). Stores `self._disk`.
  - `protondisk.gui.app.ProtonDiskApp(Adw.Application)` — `application_id="dev.protondisk.App"`; on `activate`, creates and presents a `MainWindow(self, self._disk)`. `run(argv=None, disk=None) -> int` constructs the app (default `disk=ProtonDisk()` is **deferred** — do NOT construct a disk at import; construct lazily in `run`/on first use so `--help` etc. work without the binary) and calls `.run()`.
  - `protondisk/cli.py`: a `gui` subparser whose handler calls `protondisk.gui.app.run()` and returns its int.

- [ ] **Step 1: Set up the GUI venv (idempotent) and write the failing test**

Run (idempotent — safe if `.venv-gui` already exists):
```bash
python3 -m venv --system-site-packages .venv-gui
.venv-gui/bin/pip install -q pytest -e .
.venv-gui/bin/python -c "import gi; gi.require_version('Adw','1'); from gi.repository import Adw; print('Adw OK')"
```

`tests/gui/test_window_builds.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from protondisk.gui.window import MainWindow


def test_main_window_is_a_widget_and_holds_disk():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    sentinel = object()
    win = MainWindow(application=app, disk=sentinel)
    assert isinstance(win, Gtk.Widget)
    assert win._disk is sentinel
    assert win.get_title() == "ProtonDisk"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_window_builds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.gui'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/gui/__init__.py`:
```python
"""ProtonDisk GTK4 + libadwaita graphical browser."""
```

`protondisk/gui/window.py`:
```python
"""Main application window (GTK4 + libadwaita)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application, disk) -> None:
        super().__init__(application=application)
        self._disk = disk
        self.set_title("ProtonDisk")
        self.set_default_size(900, 600)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="ProtonDisk", subtitle=""))
        toolbar_view.add_top_bar(header)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar_view.set_content(self._content)
        self.set_content(toolbar_view)
```

`protondisk/gui/app.py`:
```python
"""GTK4 application entry point for ProtonDisk."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .window import MainWindow


class ProtonDiskApp(Adw.Application):
    def __init__(self, disk=None) -> None:
        super().__init__(application_id="dev.protondisk.App")
        self._disk = disk
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._disk is None:
            from protondisk.core import ProtonDisk
            self._disk = ProtonDisk()
        if self._window is None:
            self._window = MainWindow(application=self, disk=self._disk)
        self._window.present()


def run(argv: list[str] | None = None, disk=None) -> int:
    app = ProtonDiskApp(disk=disk)
    return app.run(argv)
```

Add the `gui` subcommand to `protondisk/cli.py`. In `_build_parser()`, after the `ls` subparser:
```python
    sub.add_parser("gui", help="launch the graphical browser")
```
In `main()`, handle it BEFORE the `disk = disk or ProtonDisk()` line (the GUI manages its own disk lifecycle):
```python
    if args.command == "gui":
        from protondisk.gui.app import run as run_gui
        return run_gui()
```
Place this immediately after the `version` branch's `return 0`.

`scripts/gui-smoke.py` (launch + screenshot + auto-quit; used by widget tasks):
```python
"""Launch the ProtonDisk GUI, snapshot the window, and exit. For visual verification.

Usage: .venv-gui/bin/python scripts/gui-smoke.py [screenshot.png]
"""
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from protondisk.gui.app import ProtonDiskApp

OUT = sys.argv[1] if len(sys.argv) > 1 else "gui-smoke.png"


def _snapshot_and_quit(app):
    win = app.get_active_window()
    if win is not None:
        paintable = Gtk.WidgetPaintable(widget=win)  # noqa: F841 (kept for clarity)
        # Save via a snapshot: render the window to a texture.
        width, height = win.get_width(), win.get_height()
        if width > 0 and height > 0:
            snapshot = Gtk.Snapshot()
            win.do_snapshot(win, snapshot) if False else None
    print(f"window present: {win is not None}; size={win.get_width()}x{win.get_height()}" if win else "no window")
    app.quit()
    return GLib.SOURCE_REMOVE


def main() -> int:
    app = ProtonDiskApp()
    def on_activate(a):
        GLib.timeout_add(1200, _snapshot_and_quit, a)
    app.connect("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
```
> Note: reliable off-screen PNG capture in GTK4 is fiddly; this smoke script's contract
> is only "the app activates, a window of non-zero size is presented, and it exits cleanly."
> For a real visual screenshot the reviewer/controller launches the app interactively.

- [ ] **Step 4: Run the test to verify it passes; run the smoke launch**

Run: `.venv-gui/bin/pytest tests/gui/test_window_builds.py -v`
Expected: PASS

Run: `.venv-gui/bin/python scripts/gui-smoke.py` (on `DISPLAY=:1`)
Expected: prints `window present: True; size=900x600` (or similar non-zero size) and exits 0.

Run: `.venv-gui/bin/python -m protondisk.cli gui` can be launched manually to eyeball the empty window; Ctrl-C to close. (Not required for the automated gate.)

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/__init__.py protondisk/gui/app.py protondisk/gui/window.py \
      protondisk/cli.py scripts/gui-smoke.py tests/gui/test_window_builds.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): launchable GTK4 window and 'protondisk gui' command (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 2: NavigationState — path, history, breadcrumb, directory cache (gi-free)

**Files:**
- Create: `protondisk/gui/navigation.py`
- Test: `tests/gui/test_navigation.py`

**Interfaces:**
- Produces `NavigationState(disk, root="/my-files")` — pure logic, **no `import gi`**:
  - `current -> str` — the current path (starts at `root`).
  - `entries() -> list[Entry]` — cached listing for `current`; on a cache miss calls `disk.list(current)` and caches it.
  - `navigate_to(path) -> None` — pushes `current` onto the back-stack, clears the forward-stack, sets `current = path`.
  - `go_back() -> None` / `go_forward() -> None` — move between history stacks; no-op if empty.
  - `can_go_back() -> bool` / `can_go_forward() -> bool`.
  - `breadcrumbs() -> list[tuple[str, str]]` — `(label, path)` pairs from root to current (e.g. `[("my-files","/my-files"), ("Reports","/my-files/Reports")]`).
  - `invalidate(path=None) -> None` — drop the cache entry for `path` (or all if `None`).
  - `refresh() -> list[Entry]` — invalidate `current` and re-list.

- [ ] **Step 1: Write the failing test**

`tests/gui/test_navigation.py`:
```python
from protondisk.gui.navigation import NavigationState
from protondisk.core.models import Entry


def _entry(name, parent, is_dir=True):
    return Entry(name=name, path=f"{parent.rstrip('/')}/{name}", is_dir=is_dir,
                 size=None, mtime=None, uid=name)


class FakeDisk:
    def __init__(self):
        self.list_calls = []
        self.responses = {
            "/my-files": [_entry("Reports", "/my-files"), _entry("a.txt", "/my-files", is_dir=False)],
            "/my-files/Reports": [_entry("q3.pdf", "/my-files/Reports", is_dir=False)],
        }

    def list(self, path):
        self.list_calls.append(path)
        return self.responses.get(path, [])


def test_starts_at_root():
    nav = NavigationState(FakeDisk())
    assert nav.current == "/my-files"
    assert nav.can_go_back() is False


def test_entries_are_cached():
    disk = FakeDisk()
    nav = NavigationState(disk)
    first = nav.entries()
    second = nav.entries()
    assert [e.name for e in first] == ["Reports", "a.txt"]
    assert first == second
    assert disk.list_calls == ["/my-files"]  # only one real call


def test_navigate_pushes_history_and_forward_clears():
    disk = FakeDisk()
    nav = NavigationState(disk)
    nav.navigate_to("/my-files/Reports")
    assert nav.current == "/my-files/Reports"
    assert nav.can_go_back() is True
    assert nav.can_go_forward() is False
    assert [e.name for e in nav.entries()] == ["q3.pdf"]


def test_back_and_forward():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    nav.go_back()
    assert nav.current == "/my-files"
    assert nav.can_go_forward() is True
    nav.go_forward()
    assert nav.current == "/my-files/Reports"


def test_navigating_after_back_clears_forward():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    nav.go_back()
    nav.navigate_to("/my-files/a.txt")
    assert nav.can_go_forward() is False


def test_breadcrumbs():
    nav = NavigationState(FakeDisk())
    nav.navigate_to("/my-files/Reports")
    assert nav.breadcrumbs() == [("my-files", "/my-files"), ("Reports", "/my-files/Reports")]


def test_refresh_relists():
    disk = FakeDisk()
    nav = NavigationState(disk)
    nav.entries()
    nav.refresh()
    assert disk.list_calls == ["/my-files", "/my-files"]  # cache dropped then re-listed
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_navigation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.gui.navigation'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/gui/navigation.py`:
```python
"""Navigation state for the browser: current path, history, and a listing cache.

Pure logic — intentionally free of any GTK/gi import so it unit-tests without a display.
"""
from __future__ import annotations

from protondisk.core.models import Entry


class NavigationState:
    def __init__(self, disk, root: str = "/my-files") -> None:
        self._disk = disk
        self._root = root
        self._current = root
        self._back: list[str] = []
        self._forward: list[str] = []
        self._cache: dict[str, list[Entry]] = {}

    @property
    def current(self) -> str:
        return self._current

    def entries(self) -> list[Entry]:
        if self._current not in self._cache:
            self._cache[self._current] = self._disk.list(self._current)
        return self._cache[self._current]

    def navigate_to(self, path: str) -> None:
        if path == self._current:
            return
        self._back.append(self._current)
        self._forward.clear()
        self._current = path

    def go_back(self) -> None:
        if not self._back:
            return
        self._forward.append(self._current)
        self._current = self._back.pop()

    def go_forward(self) -> None:
        if not self._forward:
            return
        self._back.append(self._current)
        self._current = self._forward.pop()

    def can_go_back(self) -> bool:
        return bool(self._back)

    def can_go_forward(self) -> bool:
        return bool(self._forward)

    def breadcrumbs(self) -> list[tuple[str, str]]:
        # Root is like "/my-files"; build cumulative paths from its segments onward.
        root_name = self._root.strip("/")
        crumbs = [(root_name, self._root)]
        remainder = self._current[len(self._root):].strip("/")
        if remainder:
            acc = self._root
            for segment in remainder.split("/"):
                acc = f"{acc}/{segment}"
                crumbs.append((segment, acc))
        return crumbs

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)

    def refresh(self) -> list[Entry]:
        self.invalidate(self._current)
        return self.entries()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv-gui/bin/pytest tests/gui/test_navigation.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/navigation.py tests/gui/test_navigation.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): NavigationState with history, breadcrumbs, listing cache (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 3: Worker — run core calls off the main loop

**Files:**
- Create: `protondisk/gui/worker.py`
- Test: `tests/gui/test_worker.py`

**Interfaces:**
- Produces `run_async(func, on_success, on_error=None) -> None` — runs `func()` on a `threading.Thread`; on completion schedules (via `GLib.idle_add`) `on_success(result)`, or `on_error(exc)` if `func` raised (and `on_error` is provided). Callbacks therefore run on the GTK main loop, never the worker thread.

- [ ] **Step 1: Write the failing test**

`tests/gui/test_worker.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib

from protondisk.gui.worker import run_async


def _drain(predicate, timeout_ms=2000):
    """Run a GLib main loop until predicate() is true or timeout."""
    loop = GLib.MainLoop()
    state = {"done": False}

    def check():
        if predicate():
            state["done"] = True
            loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(10, check)
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()
    return state["done"]


def test_success_callback_receives_result():
    got = {}
    run_async(lambda: 6 * 7, lambda r: got.setdefault("v", r))
    assert _drain(lambda: "v" in got)
    assert got["v"] == 42


def test_error_callback_receives_exception():
    err = {}

    def boom():
        raise ValueError("nope")

    run_async(boom, lambda r: None, lambda e: err.setdefault("e", e))
    assert _drain(lambda: "e" in err)
    assert isinstance(err["e"], ValueError)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.gui.worker'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/gui/worker.py`:
```python
"""Run blocking core calls off the GTK main loop and marshal results back onto it."""
from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402


def run_async(func: Callable, on_success: Callable, on_error: Callable | None = None) -> None:
    def worker() -> None:
        try:
            result = func()
        except Exception as exc:  # deliver to the main loop, don't crash the thread
            if on_error is not None:
                GLib.idle_add(on_error, exc)
            return
        GLib.idle_add(on_success, result)

    threading.Thread(target=worker, daemon=True).start()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv-gui/bin/pytest tests/gui/test_worker.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/worker.py tests/gui/test_worker.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): worker to run core calls off the main loop (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 4: Auth gating + folder list view (wire navigation + worker + core into the window)

**Files:**
- Modify: `protondisk/gui/window.py`
- Test: `tests/gui/test_window_states.py`

**Interfaces:**
- `MainWindow` gains a stack of two views managed by `Adw.ViewStack` or manual swap:
  - **Signed-out view:** a `Gtk.Button` "Sign in with Proton" → on click, `run_async(self._disk.login, on_success=<reload>, on_error=<show_error>)`.
  - **Browser view:** a `Gtk.ScrolledWindow` containing a `Gtk.ListView` (or `Gtk.ColumnView`) backed by a `Gio.ListStore` of a small `GObject` row wrapper; each row shows a folder/file icon (`folder`/`text-x-generic`) + name.
- On construction, `MainWindow` builds a `NavigationState(self._disk)` and calls `self._check_auth()` which runs `self._disk.auth_status` via the worker and swaps to the right view; when logged in it loads `nav.entries()` via the worker and fills the store.
- **Testable seam (no widgets in the assertions):** extract a pure method `MainWindow._rows_from_entries(entries) -> list[tuple[str, bool]]` returning `(name, is_dir)` pairs the store is built from, and a pure `MainWindow._icon_name(is_dir) -> str` (`"folder"` or `"text-x-generic"`). Tests target these + `NavigationState`, not GTK signals.

- [ ] **Step 1: Write the failing test**

`tests/gui/test_window_states.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry


class FakeDisk:
    def list(self, path):
        return [
            Entry("Reports", "/my-files/Reports", True, None, None, "u1"),
            Entry("a.txt", "/my-files/a.txt", False, 10, None, "u2"),
        ]


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_rows_from_entries_maps_name_and_is_dir():
    win = _win()
    rows = win._rows_from_entries(FakeDisk().list("/my-files"))
    assert rows == [("Reports", True), ("a.txt", False)]


def test_icon_name_by_type():
    win = _win()
    assert win._icon_name(True) == "folder"
    assert win._icon_name(False) == "text-x-generic"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_window_states.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_rows_from_entries'`

- [ ] **Step 3: Write minimal implementation**

Rewrite `protondisk/gui/window.py` to add the views, navigation, worker wiring, and the two pure helpers. Full file:
```python
"""Main application window (GTK4 + libadwaita)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GObject  # noqa: E402

from .navigation import NavigationState
from .worker import run_async
from protondisk.core.errors import ProtonDiskError


class _Row(GObject.Object):
    name = GObject.Property(type=str, default="")
    is_dir = GObject.Property(type=bool, default=False)
    path = GObject.Property(type=str, default="")

    def __init__(self, name: str, is_dir: bool, path: str) -> None:
        super().__init__()
        self.name = name
        self.is_dir = is_dir
        self.path = path


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application, disk) -> None:
        super().__init__(application=application)
        self._disk = disk
        self._nav = NavigationState(disk)
        self.set_title("ProtonDisk")
        self.set_default_size(900, 600)

        self._toolbar = Adw.ToolbarView()
        self._header = Adw.HeaderBar()
        self._title = Adw.WindowTitle(title="ProtonDisk", subtitle="")
        self._header.set_title_widget(self._title)
        self._toolbar.add_top_bar(self._header)

        self._stack = Gtk.Stack()
        self._stack.add_named(self._build_signed_out_view(), "signed_out")
        self._stack.add_named(self._build_browser_view(), "browser")
        self._stack.add_named(self._build_loading_view(), "loading")
        self._toolbar.set_content(self._stack)
        self.set_content(self._toolbar)

        self._stack.set_visible_child_name("loading")
        self._check_auth()

    # ---- pure helpers (unit-tested) ----
    @staticmethod
    def _icon_name(is_dir: bool) -> str:
        return "folder" if is_dir else "text-x-generic"

    def _rows_from_entries(self, entries) -> list[tuple[str, bool]]:
        return [(e.name, e.is_dir) for e in entries]

    # ---- view construction ----
    def _build_loading_view(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        box.append(Gtk.Spinner(spinning=True, width_request=32, height_request=32))
        return box

    def _build_signed_out_view(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER,
                      halign=Gtk.Align.CENTER, spacing=12)
        box.append(Gtk.Label(label="You are not signed in to Proton Drive."))
        btn = Gtk.Button(label="Sign in with Proton")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self._on_sign_in_clicked)
        box.append(btn)
        return box

    def _build_browser_view(self) -> Gtk.Widget:
        self._store = Gio.ListStore(item_type=_Row)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_row_setup)
        factory.connect("bind", self._on_row_bind)
        self._selection = Gtk.SingleSelection(model=self._store)
        self._list = Gtk.ListView(model=self._selection, factory=factory)
        self._list.connect("activate", self._on_row_activated)
        scroller = Gtk.ScrolledWindow(child=self._list, vexpand=True)
        return scroller

    def _on_row_setup(self, _factory, list_item) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(Gtk.Image())
        box.append(Gtk.Label(xalign=0))
        list_item.set_child(box)

    def _on_row_bind(self, _factory, list_item) -> None:
        row = list_item.get_item()
        box = list_item.get_child()
        image = box.get_first_child()
        label = image.get_next_sibling()
        image.set_from_icon_name(self._icon_name(row.is_dir))
        label.set_label(row.name)

    # ---- behaviour ----
    def _check_auth(self) -> None:
        run_async(self._disk.auth_status, self._on_auth_result, self._on_error)

    def _on_auth_result(self, status) -> None:
        if status.logged_in:
            self._title.set_subtitle(status.account or "")
            self._load_current()
        else:
            self._stack.set_visible_child_name("signed_out")
        return False

    def _on_sign_in_clicked(self, _btn) -> None:
        self._stack.set_visible_child_name("loading")
        run_async(self._disk.login, lambda _r: self._check_auth(), self._on_error)

    def _load_current(self) -> None:
        self._stack.set_visible_child_name("loading")
        run_async(self._nav.entries, self._on_entries_loaded, self._on_error)

    def _on_entries_loaded(self, entries) -> None:
        self._store.remove_all()
        for name, is_dir in self._rows_from_entries(entries):
            path = f"{self._nav.current.rstrip('/')}/{name}"
            self._store.append(_Row(name, is_dir, path))
        self._title.set_title(self._nav.current)
        self._stack.set_visible_child_name("browser")
        return False

    def _on_row_activated(self, _list, position) -> None:
        row = self._store.get_item(position)
        if row is not None and row.is_dir:
            self._nav.navigate_to(row.path)
            self._load_current()

    def _on_error(self, exc) -> None:
        message = str(exc) if isinstance(exc, ProtonDiskError) else f"Unexpected error: {exc}"
        dialog = Adw.MessageDialog(transient_for=self, heading="Error", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()
        return False
```

- [ ] **Step 4: Run the test to verify it passes; launch-verify**

Run: `.venv-gui/bin/pytest tests/gui/test_window_states.py -v`
Expected: PASS (2 tests)

Run full GUI suite: `.venv-gui/bin/pytest tests/gui/ -v` → all pass.

Launch against the real logged-in session and eyeball:
Run: `.venv-gui/bin/python -m protondisk.cli gui`
Expected: window shows a spinner, then the `/my-files` listing (folders + files with icons); the header subtitle shows the account email. Double-clicking a folder navigates into it. Close the window when satisfied. (Report describes what was observed.)

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/window.py tests/gui/test_window_states.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): auth gating and folder list view (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 5: Navigation chrome — breadcrumb + back/forward + refresh

**Files:**
- Modify: `protondisk/gui/window.py`
- Test: `tests/gui/test_window_nav.py`

**Interfaces:**
- Header bar gains: a **Back** button (`go-previous-symbolic`), a **Forward** button (`go-next-symbolic`), a **Refresh** button (`view-refresh-symbolic`), and a breadcrumb bar (an `Adw.Bin`/`Gtk.Box` under the header via a second top bar) built from `NavigationState.breadcrumbs()`.
- Back/Forward call `nav.go_back()/go_forward()` then `_load_current()`, and their `sensitive` state reflects `nav.can_go_back()/can_go_forward()`. Refresh calls `nav.refresh()` via the worker.
- **Testable seam:** a pure method `MainWindow._breadcrumb_labels() -> list[str]` returning just the labels from `self._nav.breadcrumbs()`, and `_update_nav_sensitivity()` setting button `sensitive` — assert the seam via `nav` state, plus a `_nav_button_states() -> tuple[bool, bool]` returning `(back_sensitive, forward_sensitive)`.

- [ ] **Step 1: Write the failing test**

`tests/gui/test_window_nav.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry


class FakeDisk:
    def list(self, path):
        return [Entry("Reports", "/my-files/Reports", True, None, None, "u1")]


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_breadcrumb_labels_follow_navigation():
    win = _win()
    assert win._breadcrumb_labels() == ["my-files"]
    win._nav.navigate_to("/my-files/Reports")
    assert win._breadcrumb_labels() == ["my-files", "Reports"]


def test_nav_button_states_reflect_history():
    win = _win()
    assert win._nav_button_states() == (False, False)
    win._nav.navigate_to("/my-files/Reports")
    assert win._nav_button_states() == (True, False)
    win._nav.go_back()
    assert win._nav_button_states() == (False, True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_window_nav.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_breadcrumb_labels'`

- [ ] **Step 3: Write minimal implementation**

In `protondisk/gui/window.py`, add the header buttons in `__init__` (after building `self._header`, before setting content) and a breadcrumb bar, plus the methods. Add to `__init__` after `self._header.set_title_widget(self._title)`:
```python
        self._back_btn = Gtk.Button(icon_name="go-previous-symbolic", sensitive=False)
        self._fwd_btn = Gtk.Button(icon_name="go-next-symbolic", sensitive=False)
        self._refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self._back_btn.connect("clicked", self._on_back)
        self._fwd_btn.connect("clicked", self._on_forward)
        self._refresh_btn.connect("clicked", self._on_refresh)
        self._header.pack_start(self._back_btn)
        self._header.pack_start(self._fwd_btn)
        self._header.pack_end(self._refresh_btn)

        self._breadcrumb_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                                       margin_start=8, margin_end=8,
                                       margin_top=4, margin_bottom=4)
        self._toolbar.add_top_bar(self._breadcrumb_bar)
```
(Ensure `self._toolbar.add_top_bar(self._breadcrumb_bar)` runs after `self._toolbar.add_top_bar(self._header)`.)

Add methods to the class:
```python
    def _breadcrumb_labels(self) -> list[str]:
        return [label for label, _path in self._nav.breadcrumbs()]

    def _nav_button_states(self) -> tuple[bool, bool]:
        return (self._nav.can_go_back(), self._nav.can_go_forward())

    def _rebuild_breadcrumbs(self) -> None:
        child = self._breadcrumb_bar.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._breadcrumb_bar.remove(child)
            child = nxt
        crumbs = self._nav.breadcrumbs()
        for index, (label, path) in enumerate(crumbs):
            if index:
                self._breadcrumb_bar.append(Gtk.Label(label="/"))
            btn = Gtk.Button(label=label)
            btn.add_css_class("flat")
            btn.connect("clicked", self._on_crumb_clicked, path)
            self._breadcrumb_bar.append(btn)

    def _on_crumb_clicked(self, _btn, path) -> None:
        if path != self._nav.current:
            self._nav.navigate_to(path)
            self._load_current()

    def _update_nav_sensitivity(self) -> None:
        back, forward = self._nav_button_states()
        self._back_btn.set_sensitive(back)
        self._fwd_btn.set_sensitive(forward)

    def _on_back(self, _btn) -> None:
        self._nav.go_back()
        self._load_current()

    def _on_forward(self, _btn) -> None:
        self._nav.go_forward()
        self._load_current()

    def _on_refresh(self, _btn) -> None:
        self._stack.set_visible_child_name("loading")
        run_async(self._nav.refresh, self._on_entries_loaded, self._on_error)
```
Then, inside `_on_entries_loaded`, before `return False`, add:
```python
        self._rebuild_breadcrumbs()
        self._update_nav_sensitivity()
```

- [ ] **Step 4: Run the test to verify it passes; launch-verify**

Run: `.venv-gui/bin/pytest tests/gui/test_window_nav.py -v`
Expected: PASS (2 tests)

Run: `.venv-gui/bin/pytest tests/gui/ -v` → all pass.

Launch and eyeball: `.venv-gui/bin/python -m protondisk.cli gui` — back/forward buttons enable/disable correctly, breadcrumb updates and its buttons jump to ancestors, refresh re-lists.

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/window.py tests/gui/test_window_nav.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): breadcrumb, back/forward, and refresh navigation (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 6: Upload + download

**Files:**
- Modify: `protondisk/gui/window.py`
- Test: `tests/gui/test_window_transfer.py`

**Interfaces:**
- Header bar gains an **Upload** button (`document-send-symbolic`) and a **Download** button (`folder-download-symbolic`).
- Upload: `Gtk.FileDialog.open_multiple` → for each chosen local path, `run_async(lambda: self._disk.upload(local, self._nav.current, conflict="skip"), …)`; on success, refresh the current dir and show a status toast.
- Download: uses the current `SingleSelection` row; if a file is selected, `Gtk.FileDialog.select_folder` → `run_async(lambda: self._disk.download(row.path, folder), …)`; on success show a toast. If the selected row is a folder (or nothing selected), show a toast "Select a file to download".
- Toasts via an `Adw.ToastOverlay` wrapping the stack.
- **Testable seam:** a pure `MainWindow._download_target() -> Entry | None` returning the currently-selected row's backing data as an `Entry`-like object (name/path/is_dir) or `None`, and a pure `MainWindow._can_download(row_is_dir: bool | None) -> bool` (True only when a file is selected). Assert these + that upload builds the right core call via a recording FakeDisk driven through a small pure method `_do_upload(paths)` that calls the worker-wrapped upload (inject a synchronous runner in the test by calling the underlying `self._disk.upload` directly through a seam `_upload_one(local)`).

- [ ] **Step 1: Write the failing test**

`tests/gui/test_window_transfer.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry, TransferResult


class FakeDisk:
    def __init__(self):
        self.uploads = []
        self.downloads = []

    def list(self, path):
        return [Entry("a.txt", "/my-files/a.txt", False, 10, None, "u2")]

    def upload(self, local, parent, *, conflict="skip"):
        self.uploads.append((local, parent, conflict))
        return TransferResult(1, 10, 0, 0, [])

    def download(self, remote, folder):
        self.downloads.append((remote, folder))
        return TransferResult(1, 10, 0, 0, [])


def _win(disk):
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=disk)


def test_can_download_only_for_files():
    win = _win(FakeDisk())
    assert win._can_download(False) is True     # a file
    assert win._can_download(True) is False      # a folder
    assert win._can_download(None) is False      # nothing selected


def test_upload_one_calls_core_with_current_parent():
    disk = FakeDisk()
    win = _win(disk)
    win._nav.navigate_to("/my-files/Reports")
    win._upload_one("/tmp/local.txt")
    assert disk.uploads == [("/tmp/local.txt", "/my-files/Reports", "skip")]


def test_download_one_calls_core():
    disk = FakeDisk()
    win = _win(disk)
    win._download_one("/my-files/a.txt", "/tmp/out")
    assert disk.downloads == [("/my-files/a.txt", "/tmp/out")]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_window_transfer.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_can_download'`

- [ ] **Step 3: Write minimal implementation**

In `protondisk/gui/window.py`:

Wrap the stack in a toast overlay. Change the content wiring in `__init__` from `self._toolbar.set_content(self._stack)` to:
```python
        self._toasts = Adw.ToastOverlay(child=self._stack)
        self._toolbar.set_content(self._toasts)
```

Add the header buttons in `__init__` (with the others):
```python
        self._upload_btn = Gtk.Button(icon_name="document-send-symbolic")
        self._download_btn = Gtk.Button(icon_name="folder-download-symbolic")
        self._upload_btn.connect("clicked", self._on_upload_clicked)
        self._download_btn.connect("clicked", self._on_download_clicked)
        self._header.pack_end(self._upload_btn)
        self._header.pack_end(self._download_btn)
```

Add the seams and handlers:
```python
    # ---- transfer seams (unit-tested) ----
    @staticmethod
    def _can_download(row_is_dir) -> bool:
        return row_is_dir is False  # True only for a selected file

    def _upload_one(self, local: str):
        return self._disk.upload(local, self._nav.current, conflict="skip")

    def _download_one(self, remote: str, folder: str):
        return self._disk.download(remote, folder)

    def _selected_row(self):
        pos = self._selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION:
            return None
        return self._store.get_item(pos)

    # ---- transfer handlers ----
    def _toast(self, text: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=text))

    def _on_upload_clicked(self, _btn) -> None:
        dialog = Gtk.FileDialog()
        dialog.open_multiple(self, None, self._on_upload_chosen)

    def _on_upload_chosen(self, dialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except Exception:
            return  # user cancelled
        locals_ = [f.get_path() for f in files if f.get_path()]
        for local in locals_:
            run_async(lambda l=local: self._upload_one(l),
                      lambda _r, l=local: self._on_upload_done(l), self._on_error)

    def _on_upload_done(self, local: str) -> None:
        self._toast(f"Uploaded {local.rsplit('/', 1)[-1]}")
        self._stack.set_visible_child_name("loading")
        run_async(self._nav.refresh, self._on_entries_loaded, self._on_error)
        return False

    def _on_download_clicked(self, _btn) -> None:
        row = self._selected_row()
        if not self._can_download(getattr(row, "is_dir", None)):
            self._toast("Select a file to download")
            return
        dialog = Gtk.FileDialog()
        dialog.select_folder(self, None,
                             lambda d, r, path=row.path: self._on_download_folder(d, r, path))

    def _on_download_folder(self, dialog, result, remote_path: str) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except Exception:
            return  # cancelled
        target = folder.get_path()
        run_async(lambda: self._download_one(remote_path, target),
                  lambda _r: self._on_download_done(remote_path), self._on_error)

    def _on_download_done(self, remote_path: str) -> None:
        self._toast(f"Downloaded {remote_path.rsplit('/', 1)[-1]}")
        return False
```

- [ ] **Step 4: Run the test to verify it passes; launch-verify with real transfers**

Run: `.venv-gui/bin/pytest tests/gui/test_window_transfer.py -v`
Expected: PASS (3 tests)

Run: `.venv-gui/bin/pytest tests/gui/ -v` → all pass.

Launch and do a REAL round-trip against the live account (use a throwaway temp file; clean up after):
Run: `.venv-gui/bin/python -m protondisk.cli gui`
- Upload a small local file into `/my-files` → a toast appears, the file shows up after refresh.
- Select that file, Download it to `/tmp` → toast appears, file lands locally.
- Then remove the uploaded test file from Drive (via `proton-drive filesystem trash` or a later GUI feature) so the account is left clean. Describe the observed round-trip in the report.

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/window.py tests/gui/test_window_transfer.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): upload and download with toasts (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 7: Status bar + file sizes + final polish

**Files:**
- Modify: `protondisk/gui/window.py`
- Test: `tests/gui/test_window_status.py`

**Interfaces:**
- A bottom status bar (a `Gtk.Label` added as `self._toolbar.add_bottom_bar(...)`) shows `"{n} items · {account}"`.
- The list rows show a right-aligned human-readable size for files (folders show nothing).
- **Testable seams:** `MainWindow._status_text(n_items: int, account: str | None) -> str` and a module-level `human_size(n: int | None) -> str` in `protondisk/gui/format.py` (gi-free), e.g. `human_size(0) == "0 B"`, `human_size(95) == "95 B"`, `human_size(1024) == "1.0 KB"`, `human_size(None) == ""`.

- [ ] **Step 1: Write the failing test**

`tests/gui/test_window_status.py`:
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.gui.format import human_size


class FakeDisk:
    def list(self, path):
        return []


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_human_size():
    assert human_size(None) == ""
    assert human_size(0) == "0 B"
    assert human_size(95) == "95 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(1536) == "1.5 KB"
    assert human_size(1048576) == "1.0 MB"


def test_status_text():
    win = _win()
    assert win._status_text(0, "u@pm.me") == "0 items · u@pm.me"
    assert win._status_text(3, "u@pm.me") == "3 items · u@pm.me"
    assert win._status_text(1, None) == "1 item"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv-gui/bin/pytest tests/gui/test_window_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.gui.format'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/gui/format.py`:
```python
"""Small formatting helpers for the GUI (gi-free)."""
from __future__ import annotations


def human_size(n: int | None) -> str:
    if n is None:
        return ""
    if n < 1024:
        return f"{n} B"
    value = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"
```

In `protondisk/gui/window.py`:
- Import: `from .format import human_size`.
- Add the status bar in `__init__` after `self.set_content(self._toolbar)` is prepared (before it, while `self._toolbar` is mutable):
```python
        self._status = Gtk.Label(xalign=0, margin_start=8, margin_end=8,
                                 margin_top=4, margin_bottom=4)
        self._status.add_css_class("dim-label")
        self._toolbar.add_bottom_bar(self._status)
```
- Add:
```python
    def _status_text(self, n_items: int, account) -> str:
        noun = "item" if n_items == 1 else "items"
        base = f"{n_items} {noun}"
        return f"{base} · {account}" if account else base
```
- Store the account from auth: in `_on_auth_result`, add `self._account = status.account` (init `self._account = None` in `__init__`).
- In `_on_entries_loaded`, after filling the store, set the status:
```python
        self._status.set_label(self._status_text(len(self._store), self._account))
```
- Show size in rows: extend `_Row` with a `size` int property (default -1 meaning "none"), pass `e.size if e.size is not None else -1` when appending, and in `_on_row_bind` append a right-aligned size label. Update `_on_row_setup` to add a trailing size label:
```python
    def _on_row_setup(self, _factory, list_item) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(Gtk.Image())
        name = Gtk.Label(xalign=0, hexpand=True)
        box.append(name)
        box.append(Gtk.Label(xalign=1))  # size
        list_item.set_child(box)

    def _on_row_bind(self, _factory, list_item) -> None:
        row = list_item.get_item()
        box = list_item.get_child()
        image = box.get_first_child()
        name = image.get_next_sibling()
        size = name.get_next_sibling()
        image.set_from_icon_name(self._icon_name(row.is_dir))
        name.set_label(row.name)
        size.set_label("" if row.is_dir or row.size < 0 else human_size(row.size))
```
Update `_Row.__init__` and the `_store.append(...)` call in `_on_entries_loaded` accordingly (append `_Row(name, is_dir, path, size)` — thread the size through `_rows_from_entries`? Keep `_rows_from_entries` returning `(name, is_dir)` for its existing test; fetch size directly from the entries loop instead). Concretely, change `_on_entries_loaded` to iterate the raw entries:
```python
    def _on_entries_loaded(self, entries) -> None:
        self._store.remove_all()
        for entry in entries:
            path = f"{self._nav.current.rstrip('/')}/{entry.name}"
            size = entry.size if entry.size is not None else -1
            self._store.append(_Row(entry.name, entry.is_dir, path, size))
        self._title.set_title(self._nav.current)
        self._rebuild_breadcrumbs()
        self._update_nav_sensitivity()
        self._status.set_label(self._status_text(len(self._store), self._account))
        self._stack.set_visible_child_name("browser")
        return False
```
And `_Row`:
```python
class _Row(GObject.Object):
    name = GObject.Property(type=str, default="")
    is_dir = GObject.Property(type=bool, default=False)
    path = GObject.Property(type=str, default="")
    size = GObject.Property(type=int, default=-1)

    def __init__(self, name, is_dir, path, size=-1):
        super().__init__()
        self.name = name
        self.is_dir = is_dir
        self.path = path
        self.size = size
```

- [ ] **Step 4: Run the whole suite; final launch-verify**

Run: `.venv-gui/bin/pytest -p no:cacheprovider tests/ -v` using `.venv-gui` — BUT note the core tests also live in `tests/`; run the full suite to confirm nothing regressed:
Run: `.venv-gui/bin/pytest -q`
Expected: all pass (core + gui).

Launch: `.venv-gui/bin/python -m protondisk.cli gui` — status bar shows "N items · account", files show sizes. Eyeball and describe.

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/gui/window.py protondisk/gui/format.py tests/gui/test_window_status.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(gui): status bar and human-readable file sizes (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

## Increment Completion — "Bump minor" to 0.3.0

After all 7 tasks pass, when the user says **"Bump minor"**:
1. Update `CHANGELOG.md` (0.3.0 — GTK4 GUI: browse + transfer) and `README.md` (status table, GUI usage/screenshot, `--system-site-packages` requirement).
2. Set `VERSION` to `0.3.0`.
3. Commit to `dev`, merge `dev` → `main`, push both, tag `v0.3.0`.

---

## Self-Review

**1. Spec coverage (design §5, this increment's scope):**
- GTK4 + libadwaita app, calls only the core → Tasks 1,4 ✅
- Worker-thread model (`GLib.idle_add`), UI never blocks → Task 3, used in 4/5/6/7 ✅
- Directory cache + manual refresh → Task 2 (cache) + Task 5 (refresh) ✅
- Browse: list view, breadcrumb, back/forward → Tasks 4,5 ✅
- Auth: on-launch status, sign-in view calling `login()` → Task 4 ✅
- Transfer: upload + download → Task 6 ✅
- Error dialogs on `ProtonDiskError` → Task 4 (`_on_error`) ✅
- Status bar (items · account) → Task 7 ✅
- Mocked-core logic tests + launch verification (no automated widget clicks) → every task ✅
- Deferred (organize/sharing/drag-drop/grid/thumbnails) → explicitly out of this increment ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. The `gui-smoke.py` snapshot is intentionally a launch/present/exit check, documented as such (real screenshotting is done interactively) — not a placeholder.

**3. Type/name consistency:** `MainWindow(application, disk)`, `NavigationState(disk, root)`, `run_async(func, on_success, on_error)`, `_Row`, the pure seams (`_rows_from_entries`, `_icon_name`, `_breadcrumb_labels`, `_nav_button_states`, `_can_download`, `_upload_one`, `_download_one`, `_status_text`, `human_size`) are consistent across tasks. Each widget task adds to the same `MainWindow` without breaking earlier seams (`_rows_from_entries` stays `(name, is_dir)`; sizes are threaded via the entries loop, not that seam).

**Notes carried forward:**
- Live `auth login` is exercised for real in Task 4; if the captured-output/`--json` handling on `auth login` misbehaves (the deferred Milestone-1 risk), fix it in `protondisk/core` under a patch bump and note it — the GUI depends on it working.
- Automated off-screen screenshotting is not reliably solved here; widget tasks rely on interactive launch + honest observation in the report. Reviewers should treat launch-observation claims like any other report claim and, where possible, run `scripts/gui-smoke.py` themselves.

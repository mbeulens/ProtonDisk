# ProtonDisk Milestone 2 (increment 2) — GUI Organize + Sharing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file management (new folder, rename, move, trash) and sharing (status + invite) to the ProtonDisk GTK4 GUI, all on the existing `protondisk.core` façade.

**Architecture:** Extends `protondisk/gui/window.py`. New actions run through the existing `run_async` worker; results refresh the current listing. Right-click on a row opens a context menu (`Gtk.PopoverMenu` via a `Gio.Menu` + `Gtk.GestureClick`), with actions wired through a `Gio.SimpleActionGroup`. A "New Folder" header button and a "Paste" (move) affordance round it out. Sharing opens an `Adw.Window`/`Adw.MessageDialog`-based dialog.

**Tech Stack:** Python 3.12+, GTK4 + libadwaita (PyGObject), `pytest`, run under `.venv-gui`. DISPLAY `:1` for launch verification.

**This increment delivers (→ 0.4.0):** New Folder, Rename, Move (cut→paste), Trash (with confirm), and a Share dialog (see who has access + invite by email/role). **Deferred:** drag-and-drop, grid view, thumbnails, public share links, multi-select.

## Global Constraints

- **Environment:** all code/tests under **`.venv-gui`** (`.venv-gui/bin/pytest`). GUI imports only `gi` + `protondisk.core`; navigation/format/progress stay gi-free.
- **Threading:** every core call (`mkdir`, `rename`, `move`, `trash`, `sharing_status`, `sharing_invite`) runs via `run_async`; UI mutations happen on the main loop (callbacks / `GLib.idle_add`). After a mutation, re-list the current folder (`self._reload(self._nav.refresh)`).
- **Core is already built** (Milestone 1): `mkdir(path)`, `rename(path, new_name)`, `move(src, target_parent)`, `trash(path)`, `sharing_status(path) -> ShareInfo`, `sharing_invite(path, user, role="viewer", message="")`. Do NOT modify the core except where a task explicitly says so.
- **Confirmed CLI facts:** `create-folder parentPath name`; `rename path newName`; `move src… targetParent` (target is a PARENT folder); `trash path…`; `sharing invite -u USER -r ROLE(viewer|editor|admin) -m MESSAGE path`; `sharing status` prints `undefined` (→ not shared) for an unshared node and can error on undecryptable shares.
- **Versioning (project GIT rules):** `VERSION` is the single source of truth; each task commit runs `scripts/bump-patch.sh` (skips patch 13 → use commit message `To be sure to be sure!` if the skip notice fires) and pushes to `dev`. Increment done → **"Bump minor" → 0.4.0**.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'`; end messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **GENUINE verification:** actually run tests and paste REAL output; never fabricate. Widget behaviour is verified by the controller launching the app (unique app-id driver to avoid single-instance collision with a running app).

## Testability pattern (unchanged from increment 1)

Pure, gi-free *seams* are unit-tested; GTK wiring is verified by launch. Each task adds seams like `_selected_row()`, name-validation, argv-shaping, and message helpers that tests can call without a display.

---

### Task 1: New Folder

**Files:** Modify `protondisk/gui/window.py`; Test `tests/gui/test_window_newfolder.py`
**Interfaces:**
- Header button "New Folder" (`folder-new-symbolic`, tooltip "New folder").
- `_prompt_new_folder()` opens an `Adw.MessageDialog` with a `Gtk.Entry`; on "Create", validates via `_valid_new_name(name, existing)` and runs `run_async(lambda: self._disk.mkdir(f"{self._nav.current}/{name}"), refresh, error)`.
- Pure seam `_valid_new_name(name, existing_names) -> str | None`: returns an error string if the name is empty, contains "/", or already exists; else None.

- [ ] **Step 1: Write the failing test**
```python
from protondisk.gui.window import MainWindow

def test_valid_new_name():
    assert MainWindow._valid_new_name("", []) is not None
    assert MainWindow._valid_new_name("a/b", []) is not None
    assert MainWindow._valid_new_name("Reports", ["Reports"]) is not None
    assert MainWindow._valid_new_name("New", ["Reports"]) is None
```
(Put it in `tests/gui/test_window_newfolder.py` with the standard gi header + a `FakeDisk` with `auth_status`/`list` and a `_win()` helper, matching sibling gui test files.)

- [ ] **Step 2: Run test → FAIL** (`AttributeError: _valid_new_name`).
  Run: `.venv-gui/bin/pytest tests/gui/test_window_newfolder.py -v`

- [ ] **Step 3: Implement** `_valid_new_name` (staticmethod) + the header button + `_prompt_new_folder` + the mkdir handler:
```python
    @staticmethod
    def _valid_new_name(name: str, existing_names) -> str | None:
        name = name.strip()
        if not name:
            return "Name cannot be empty."
        if "/" in name:
            return "Name cannot contain '/'."
        if name in existing_names:
            return "An item with that name already exists."
        return None
```
In `__init__` add the button (near the other header buttons):
```python
        self._newfolder_btn = Gtk.Button(icon_name="folder-new-symbolic")
        self._newfolder_btn.set_tooltip_text("New folder")
        self._newfolder_btn.connect("clicked", lambda _b: self._prompt_new_folder())
        self._header.pack_start(self._newfolder_btn)
```
Handler (uses an entry dialog; on create, validate against current row names):
```python
    def _current_names(self):
        return [self._store.get_item(i).name for i in range(self._store.get_n_items())]

    def _prompt_new_folder(self) -> None:
        dialog = Adw.MessageDialog(transient_for=self, heading="New folder",
                                   body="Enter a name for the new folder.")
        entry = Gtk.Entry(activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_default_response("create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response != "create":
                return
            name = entry.get_text().strip()
            err = self._valid_new_name(name, self._current_names())
            if err:
                self._toast(err)
                return
            path = f"{self._nav.current.rstrip('/')}/{name}"
            run_async(lambda: self._disk.mkdir(path),
                      lambda _r: self._reload(self._nav.refresh), self._on_error)
        dialog.connect("response", on_response)
        dialog.present()
```

- [ ] **Step 4: Run test → PASS**; full gui suite green. Controller launch-verifies: New Folder button creates a folder that appears after refresh.

- [ ] **Step 5: Commit** (`feat(gui): new folder`, bump via `scripts/bump-patch.sh`, push).

---

### Task 2: Row context menu + Rename

**Files:** Modify `protondisk/gui/window.py`; Test `tests/gui/test_window_rename.py`
**Interfaces:**
- A right-click `Gtk.GestureClick` on the `ListView` opens a `Gtk.PopoverMenu` (built from a `Gio.Menu` with items Rename / Move / Trash / Share) positioned at the click; it first selects the row under the pointer. Actions are registered on a `Gio.SimpleActionGroup` named `row` inserted on the window (`self.insert_action_group("row", grp)`), so menu items reference `row.rename` etc. This task wires the group + the **Rename** action; Move/Trash/Share get placeholder actions filled by Tasks 3-5 (define all four actions now, each calling a handler; Move/Trash/Share handlers may be added in their tasks — to keep this task self-contained, implement all four action stubs that call `self._on_row_action_*`, with rename fully working and the others showing a "coming soon" toast, replaced in later tasks).
- Rename: `_prompt_rename(row)` → entry dialog prefilled with `row.name`; validate with `_valid_new_name` (excluding the row's own name); `run_async(lambda: self._disk.rename(row.path, new), refresh, error)`.

- [ ] **Step 1: Write the failing test** — assert a helper `_rename_is_noop(old, new) -> bool` (True when new is empty or equals old) so the seam is testable:
```python
from protondisk.gui.window import MainWindow
def test_rename_is_noop():
    assert MainWindow._rename_is_noop("a.txt", "a.txt") is True
    assert MainWindow._rename_is_noop("a.txt", "") is True
    assert MainWindow._rename_is_noop("a.txt", "b.txt") is False
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the gesture + popover + action group + `_rename_is_noop` + `_prompt_rename`. Full code:
```python
    @staticmethod
    def _rename_is_noop(old: str, new: str) -> bool:
        new = new.strip()
        return (not new) or new == old
```
In `_build_browser_view`, after creating `self._list`, add:
```python
        menu = Gio.Menu()
        menu.append("Rename", "row.rename")
        menu.append("Move here" if False else "Move", "row.move")
        menu.append("Trash", "row.trash")
        menu.append("Share…", "row.share")
        self._row_menu = Gtk.PopoverMenu.new_from_model(menu)
        self._row_menu.set_parent(self._list)
        self._row_menu.set_has_arrow(False)
        gesture = Gtk.GestureClick(button=3)  # right-click
        gesture.connect("pressed", self._on_row_right_click)
        self._list.add_controller(gesture)
        grp = Gio.SimpleActionGroup()
        for name, cb in (("rename", self._act_rename), ("move", self._act_move),
                         ("trash", self._act_trash), ("share", self._act_share)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            grp.add_action(act)
        self.insert_action_group("row", grp)
```
Handlers:
```python
    def _on_row_right_click(self, gesture, n_press, x, y) -> None:
        # select the row under the pointer, then pop the menu there
        row_height = 34
        index = int(y // row_height)
        if 0 <= index < self._store.get_n_items():
            self._selection.set_selected(index)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._row_menu.set_pointing_to(rect)
        self._row_menu.popup()

    def _act_rename(self, _action, _param) -> None:
        row = self._selected_row()
        if row is not None:
            self._prompt_rename(row)

    def _prompt_rename(self, row) -> None:
        dialog = Adw.MessageDialog(transient_for=self, heading=f"Rename “{row.name}”", body="")
        entry = Gtk.Entry(text=row.name, activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_default_response("rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        def on_response(dlg, response):
            if response != "rename":
                return
            new = entry.get_text().strip()
            if self._rename_is_noop(row.name, new):
                return
            err = self._valid_new_name(new, [n for n in self._current_names() if n != row.name])
            if err:
                self._toast(err); return
            run_async(lambda: self._disk.rename(row.path, new),
                      lambda _r: self._reload(self._nav.refresh), self._on_error)
        dialog.connect("response", on_response)
        dialog.present()
```
Add `Gdk` to the gi import: `from gi.repository import Gtk, Adw, Gio, GObject, GLib, Gdk`. Add temporary `_act_move`/`_act_trash`/`_act_share` that `self._toast("Coming soon")` (replaced in Tasks 3-5).

- [ ] **Step 4: Run → PASS**; full suite green. Controller launch-verifies: right-click a file → Rename → the file is renamed after refresh.
- [ ] **Step 5: Commit** (`feat(gui): row context menu and rename`).

---

### Task 3: Move (cut → paste)

**Files:** Modify `protondisk/gui/window.py`; Test `tests/gui/test_window_move.py`
**Interfaces:**
- `_act_move` sets `self._cut = row.path` and `self._cut_name = row.name`, toasts "Cut {name} — open a folder and press Paste", and reveals a header "Paste" button (`edit-paste-symbolic`).
- Paste button → `run_async(lambda: self._disk.move(self._cut, self._nav.current), …)`, then clears cut + hides Paste + refresh. Disabled when nothing is cut or when the current folder is the item's own parent.
- Pure seam `_can_paste_into(cut_path, current) -> bool`: False if `cut_path` is falsy, if `current` equals the cut item's parent (no-op), or if `current` is inside the cut item (can't move a folder into itself).

- [ ] **Step 1: Write the failing test**
```python
from protondisk.gui.window import MainWindow
def test_can_paste_into():
    assert MainWindow._can_paste_into("", "/my-files") is False
    assert MainWindow._can_paste_into("/my-files/a.txt", "/my-files") is False   # same parent
    assert MainWindow._can_paste_into("/my-files/Dir", "/my-files/Dir") is False # into itself
    assert MainWindow._can_paste_into("/my-files/Dir", "/my-files/Dir/sub") is False
    assert MainWindow._can_paste_into("/my-files/a.txt", "/my-files/Reports") is True
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement:**
```python
    @staticmethod
    def _can_paste_into(cut_path: str, current: str) -> bool:
        if not cut_path:
            return False
        parent = cut_path.rsplit("/", 1)[0] or "/"
        if current == parent:
            return False
        if current == cut_path or current.startswith(cut_path.rstrip("/") + "/"):
            return False
        return True
```
Add `self._cut = None` in `__init__`; a hidden `self._paste_btn = Gtk.Button(icon_name="edit-paste-symbolic", visible=False)` in the header with tooltip "Move the cut item here"; connect it to `_on_paste`. Replace the `_act_move` stub:
```python
    def _act_move(self, _action, _param) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._cut = row.path
        self._toast(f"Cut {row.name} — open a folder and press Paste")
        self._update_paste_sensitivity()

    def _update_paste_sensitivity(self) -> None:
        can = self._can_paste_into(self._cut or "", self._nav.current)
        self._paste_btn.set_visible(bool(self._cut))
        self._paste_btn.set_sensitive(can)

    def _on_paste(self, _btn) -> None:
        if not self._can_paste_into(self._cut or "", self._nav.current):
            return
        src = self._cut
        run_async(lambda: self._disk.move(src, self._nav.current),
                  lambda _r: self._after_paste(), self._on_error)

    def _after_paste(self) -> None:
        self._cut = None
        self._paste_btn.set_visible(False)
        self._reload(self._nav.refresh)
        return False
```
Call `self._update_paste_sensitivity()` at the end of `_on_entries_loaded` (so Paste enable-state tracks the folder you navigate to).

- [ ] **Step 4: Run → PASS**; suite green. Controller launch-verifies: right-click → Move, navigate into a folder, Paste → item moves.
- [ ] **Step 5: Commit** (`feat(gui): move via cut and paste`).

---

### Task 4: Trash (with confirmation)

**Files:** Modify `protondisk/gui/window.py`; Test `tests/gui/test_window_trash.py`
**Interfaces:**
- `_act_trash` → an `Adw.MessageDialog` confirm ("Move “{name}” to trash?", destructive "Move to Trash"). On confirm, `run_async(lambda: self._disk.trash(row.path), refresh, error)` + toast "Moved {name} to trash".
- Pure seam `_trash_confirm_text(name) -> str` returning the heading string, so wording is testable.

- [ ] **Step 1: Write the failing test**
```python
from protondisk.gui.window import MainWindow
def test_trash_confirm_text():
    assert MainWindow._trash_confirm_text("a.txt") == "Move “a.txt” to trash?"
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement:**
```python
    @staticmethod
    def _trash_confirm_text(name: str) -> str:
        return f"Move “{name}” to trash?"

    def _act_trash(self, _action, _param) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = Adw.MessageDialog(transient_for=self,
                                   heading=self._trash_confirm_text(row.name), body="")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("trash", "Move to Trash")
        dialog.set_response_appearance("trash", Adw.ResponseAppearance.DESTRUCTIVE)
        def on_response(dlg, response, path=row.path, name=row.name):
            if response != "trash":
                return
            run_async(lambda: self._disk.trash(path),
                      lambda _r: self._after_trash(name), self._on_error)
        dialog.connect("response", on_response)
        dialog.present()

    def _after_trash(self, name: str) -> None:
        self._toast(f"Moved {name} to trash")
        self._reload(self._nav.refresh)
        return False
```
- [ ] **Step 4: Run → PASS**; suite green. Controller launch-verifies against a throwaway file (upload → trash via menu → gone), Drive left clean.
- [ ] **Step 5: Commit** (`feat(gui): trash with confirmation`).

---

### Task 5: Share dialog (status + invite)

**Files:** Modify `protondisk/gui/window.py`; Test `tests/gui/test_window_share.py`
**Interfaces:**
- `_act_share` → `run_async(lambda: self._disk.sharing_status(row.path), on_share_status, on_error)`; the callback opens an `Adw.MessageDialog` showing whether the item is shared and current members, plus a `Gtk.Entry` for an email and a `Gtk.DropDown` for the role (viewer/editor/admin). On "Invite", validate the email with `_valid_email(email)` then `run_async(lambda: self._disk.sharing_invite(row.path, email, role), on_invited, on_error)`.
- Pure seams: `_valid_email(email) -> bool` (contains "@" and "." after it, non-empty local part) and `_share_summary(info) -> str` (e.g. "Shared with 2 people" / "Not shared") from a `ShareInfo`.

- [ ] **Step 1: Write the failing test**
```python
from protondisk.gui.window import MainWindow
from protondisk.core.models import ShareInfo
def test_valid_email():
    assert MainWindow._valid_email("a@pm.me") is True
    assert MainWindow._valid_email("nope") is False
    assert MainWindow._valid_email("@pm.me") is False
    assert MainWindow._valid_email("a@b") is False
def test_share_summary():
    assert MainWindow._share_summary(ShareInfo("/p", False, [])) == "Not shared"
    assert MainWindow._share_summary(ShareInfo("/p", True, ["a@pm.me"])) == "Shared with 1 person"
    assert MainWindow._share_summary(ShareInfo("/p", True, ["a@pm.me", "b@pm.me"])) == "Shared with 2 people"
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the two seams + the share flow:
```python
    @staticmethod
    def _valid_email(email: str) -> bool:
        email = email.strip()
        if "@" not in email:
            return False
        local, _, domain = email.partition("@")
        return bool(local) and "." in domain and not domain.endswith(".")

    @staticmethod
    def _share_summary(info) -> str:
        if not info.shared:
            return "Not shared"
        n = len(info.members)
        return f"Shared with {n} {'person' if n == 1 else 'people'}"

    def _act_share(self, _action, _param) -> None:
        row = self._selected_row()
        if row is None:
            return
        run_async(lambda: self._disk.sharing_status(row.path),
                  lambda info, r=row: self._open_share_dialog(r, info), self._on_error)

    def _open_share_dialog(self, row, info) -> None:
        dialog = Adw.MessageDialog(transient_for=self, heading=f"Share “{row.name}”",
                                   body=self._share_summary(info))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        email = Gtk.Entry(placeholder_text="colleague@example.com")
        roles = Gtk.StringList.new(["viewer", "editor", "admin"])
        role_dd = Gtk.DropDown(model=roles)
        box.append(email)
        box.append(role_dd)
        dialog.set_extra_child(box)
        dialog.add_response("close", "Close")
        dialog.add_response("invite", "Invite")
        dialog.set_default_response("invite")
        dialog.set_response_appearance("invite", Adw.ResponseAppearance.SUGGESTED)
        def on_response(dlg, response, path=row.path):
            if response != "invite":
                return
            addr = email.get_text().strip()
            if not self._valid_email(addr):
                self._toast("Enter a valid email address."); return
            role = ["viewer", "editor", "admin"][role_dd.get_selected()]
            run_async(lambda: self._disk.sharing_invite(path, addr, role),
                      lambda _r, a=addr: self._toast(f"Invited {a}"), self._on_error)
        dialog.connect("response", on_response)
        dialog.present()
```
Replace the Task-2 `_act_share` stub with this. Remove the temporary `_act_move`/`_act_trash`/`_act_share` stubs entirely once their real versions land (Tasks 3/4/5).

- [ ] **Step 4: Run → PASS**; full suite green. Controller launch-verifies: right-click a folder → Share… shows "Not shared" and the invite form (does NOT send a real invite to a stranger during verification — verify the dialog builds and `_valid_email` gates; a real invite is optional and only to the user's own alias).
- [ ] **Step 5: Commit** (`feat(gui): share dialog with status and invite`).

---

## Increment Completion — "Bump minor" to 0.4.0

After all 5 tasks pass, when the user says **"Bump minor"**: update `CHANGELOG.md` (0.4.0 — GUI organize + sharing) and `README.md`; set `VERSION` to `0.4.0`; commit to `dev`, merge `dev` → `main`, push both, tag `v0.4.0`.

## Self-Review

**Spec coverage (design §5 organize + sharing):** New Folder (T1), Rename (T2), Move (T3), Trash (T4), Share status+invite (T5) — all present. Deferred (drag-drop, grid, thumbnails, public links, multi-select) explicitly out.
**Placeholder scan:** every step has complete code; the Task-2 Move/Trash/Share action *stubs* are explicitly temporary and replaced in Tasks 3-5 (not TBDs).
**Type consistency:** `_selected_row()`, `_current_names()`, `_reload(self._nav.refresh)`, the `row` action group, and the pure seams (`_valid_new_name`, `_rename_is_noop`, `_can_paste_into`, `_trash_confirm_text`, `_valid_email`, `_share_summary`) are consistent across tasks. All mutations refresh via `_reload`.
**Note:** `sharing status` can raise on undecryptable shares (e.g. an already-shared root) — `_act_share`'s `on_error` surfaces that via the normal error dialog; acceptable for this increment.

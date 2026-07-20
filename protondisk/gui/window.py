"""Main application window (GTK4 + libadwaita)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GObject, GLib  # noqa: E402

from .navigation import NavigationState
from .worker import run_async
from .format import human_size
from protondisk.core.errors import ProtonDiskError


class _Row(GObject.Object):
    name = GObject.Property(type=str, default="")
    is_dir = GObject.Property(type=bool, default=False)
    path = GObject.Property(type=str, default="")
    size = GObject.Property(type=int, default=-1)

    def __init__(self, name: str, is_dir: bool, path: str, size: int = -1) -> None:
        super().__init__()
        self.name = name
        self.is_dir = is_dir
        self.path = path
        self.size = size


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application, disk) -> None:
        super().__init__(application=application)
        self._disk = disk
        self._nav = NavigationState(disk)
        self._load_gen = 0
        self._account = None
        self.set_title("ProtonDisk")
        self.set_default_size(900, 600)

        self._toolbar = Adw.ToolbarView()
        self._header = Adw.HeaderBar()
        self._title = Adw.WindowTitle(title="ProtonDisk", subtitle="")
        self._header.set_title_widget(self._title)
        self._back_btn = Gtk.Button(icon_name="go-previous-symbolic", sensitive=False)
        self._fwd_btn = Gtk.Button(icon_name="go-next-symbolic", sensitive=False)
        self._refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self._upload_btn = Gtk.Button(
            child=Adw.ButtonContent(icon_name="go-up-symbolic", label="Upload"))
        self._upload_btn.set_tooltip_text("Upload files into this folder")
        self._download_btn = Gtk.Button(
            child=Adw.ButtonContent(icon_name="go-down-symbolic", label="Download"))
        self._download_btn.set_tooltip_text("Download the selected file")
        self._back_btn.connect("clicked", self._on_back)
        self._fwd_btn.connect("clicked", self._on_forward)
        self._refresh_btn.connect("clicked", self._on_refresh)
        self._upload_btn.connect("clicked", self._on_upload_clicked)
        self._download_btn.connect("clicked", self._on_download_clicked)
        self._header.pack_start(self._back_btn)
        self._header.pack_start(self._fwd_btn)
        self._header.pack_end(self._refresh_btn)
        self._header.pack_end(self._upload_btn)
        self._header.pack_end(self._download_btn)
        self._toolbar.add_top_bar(self._header)

        self._breadcrumb_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                                       margin_start=8, margin_end=8,
                                       margin_top=4, margin_bottom=4)
        self._toolbar.add_top_bar(self._breadcrumb_bar)

        self._stack = Gtk.Stack()
        self._stack.add_named(self._build_signed_out_view(), "signed_out")
        self._stack.add_named(self._build_browser_view(), "browser")
        self._stack.add_named(self._build_loading_view(), "loading")
        self._toasts = Adw.ToastOverlay(child=self._stack)
        self._toolbar.set_content(self._toasts)

        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                             margin_start=8, margin_end=8, margin_top=4, margin_bottom=4)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("dim-label")
        status_bar.append(self._spinner)
        status_bar.append(self._status)
        self._toolbar.add_bottom_bar(status_bar)
        self._active_transfers = 0

        self.set_content(self._toolbar)

        self._stack.set_visible_child_name("loading")
        self._check_auth()

    # ---- pure helpers (unit-tested) ----
    @staticmethod
    def _icon_name(is_dir: bool) -> str:
        return "folder" if is_dir else "text-x-generic"

    def _rows_from_entries(self, entries) -> list[tuple[str, bool]]:
        return [(e.name, e.is_dir) for e in entries]

    def _breadcrumb_labels(self) -> list[str]:
        return [label for label, _path in self._nav.breadcrumbs()]

    def _nav_button_states(self) -> tuple[bool, bool]:
        return (self._nav.can_go_back(), self._nav.can_go_forward())

    def _status_text(self, n_items: int, account) -> str:
        noun = "item" if n_items == 1 else "items"
        base = f"{n_items} {noun}"
        return f"{base} · {account}" if account else base

    @staticmethod
    def _activity_text(kind: str, name: str) -> str:
        verb = "Uploading" if kind == "upload" else "Downloading"
        return f"{verb} {name}…"

    # ---- transfer activity indicator (throbber + phase in the status bar) ----
    def _begin_activity(self, text: str) -> None:
        self._active_transfers += 1
        self._spinner.set_visible(True)
        self._spinner.start()
        self._status.set_label(text)

    def _set_activity_phase(self, name: str, phase: str) -> None:
        # phase is a verbose label like "Encrypting…"; show it with the file name
        if self._active_transfers > 0:
            self._status.set_label(f"{phase} {name}")
        return False

    def _end_activity(self) -> None:
        self._active_transfers = max(0, self._active_transfers - 1)
        if self._active_transfers == 0:
            self._spinner.stop()
            self._spinner.set_visible(False)
            self._status.set_label(self._status_text(len(self._store), self._account))

    def _progress_cb(self, name: str):
        # returned callable runs on the worker thread; marshal onto the main loop
        return lambda phase: GLib.idle_add(self._set_activity_phase, name, phase)

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

    # ---- behaviour ----
    def _check_auth(self) -> None:
        run_async(self._disk.auth_status, self._on_auth_result, self._on_error)

    def _on_auth_result(self, status) -> None:
        self._account = status.account
        if status.logged_in:
            self._title.set_subtitle(status.account or "")
            self._load_current()
        else:
            self._stack.set_visible_child_name("signed_out")
        return False

    def _on_sign_in_clicked(self, _btn) -> None:
        self._stack.set_visible_child_name("loading")
        run_async(self._disk.login, lambda _r: self._check_auth(), self._on_error)

    def _reload(self, func) -> None:
        self._stack.set_visible_child_name("loading")
        self._load_gen += 1
        gen = self._load_gen
        run_async(func,
                  lambda entries: self._on_entries_loaded(entries, gen),
                  lambda exc: self._on_error(exc, gen))

    def _load_current(self) -> None:
        self._reload(self._nav.entries)

    def _on_entries_loaded(self, entries, gen) -> None:
        if gen != self._load_gen:
            return False  # stale response; a newer navigation superseded it
        self._store.remove_all()
        for entry in entries:
            size = entry.size if entry.size is not None else -1
            self._store.append(_Row(entry.name, entry.is_dir, entry.path, size))
        self._title.set_title(self._nav.current)
        self._rebuild_breadcrumbs()
        self._update_nav_sensitivity()
        self._status.set_label(self._status_text(len(self._store), self._account))
        self._stack.set_visible_child_name("browser")
        return False

    def _on_row_activated(self, _list, position) -> None:
        row = self._store.get_item(position)
        if row is not None and row.is_dir:
            self._nav.navigate_to(row.path)
            self._load_current()

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
        self._reload(self._nav.refresh)

    def _on_error(self, exc, gen=None) -> None:
        if gen is not None and gen != self._load_gen:
            return False  # a newer load superseded this one
        message = str(exc) if isinstance(exc, ProtonDiskError) else f"Unexpected error: {exc}"
        dialog = Adw.MessageDialog(transient_for=self, heading="Error", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()
        # never leave the user stranded on the loading spinner
        self._stack.set_visible_child_name(self._recovery_view())
        return False

    def _recovery_view(self) -> str:
        # a signed-in user with an empty folder still belongs in the browser
        return "browser" if (self._store.get_n_items() or self._account) else "signed_out"

    # ---- transfer seams (unit-tested) ----
    @staticmethod
    def _can_download(row_is_dir) -> bool:
        return row_is_dir is False  # True only for a selected file

    def _upload_one(self, local: str, progress=None):
        return self._disk.upload(local, self._nav.current, conflict="skip", progress=progress)

    def _download_one(self, remote: str, folder: str, progress=None):
        return self._disk.download(remote, folder, progress=progress)

    def _selected_row(self):
        pos = self._selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION:
            return None
        return self._store.get_item(pos)

    # ---- transfer handlers ----
    def _toast(self, text: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=text))

    @staticmethod
    def _is_dialog_cancel(exc) -> bool:
        # a dismissed file dialog is a normal cancel, not an error to report
        return (isinstance(exc, GLib.Error)
                and exc.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED))

    @staticmethod
    def _upload_result_message(name: str, result) -> str:
        if result is not None and result.skipped_items and not result.transferred_items:
            return f"Skipped {name} (already exists)"
        return f"Uploaded {name}"

    def _on_upload_clicked(self, _btn) -> None:
        dialog = Gtk.FileDialog()
        dialog.open_multiple(self, None, self._on_upload_chosen)

    def _on_upload_chosen(self, dialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error as exc:
            if not self._is_dialog_cancel(exc):
                self._on_error(exc)
            return
        locals_ = [f.get_path() for f in files if f.get_path()]
        for local in locals_:
            name = local.rsplit("/", 1)[-1]
            self._begin_activity(self._activity_text("upload", name))
            run_async(
                lambda l=local, n=name: self._upload_one(l, progress=self._progress_cb(n)),
                lambda r, l=local: self._on_upload_done(l, r),
                self._on_transfer_error)

    def _on_upload_done(self, local: str, result=None) -> None:
        self._end_activity()
        self._toast(self._upload_result_message(local.rsplit("/", 1)[-1], result))
        if self._active_transfers == 0:  # refresh once, after the last upload finishes
            self._reload(self._nav.refresh)
        return False

    def _on_transfer_error(self, exc) -> None:
        self._end_activity()
        self._on_error(exc)
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
        except GLib.Error as exc:
            if not self._is_dialog_cancel(exc):
                self._on_error(exc)
            return
        target = folder.get_path()
        name = remote_path.rsplit("/", 1)[-1]
        self._begin_activity(self._activity_text("download", name))
        run_async(
            lambda: self._download_one(remote_path, target, progress=self._progress_cb(name)),
            lambda _r: self._on_download_done(remote_path),
            self._on_transfer_error)

    def _on_download_done(self, remote_path: str) -> None:
        self._end_activity()
        self._toast(f"Downloaded {remote_path.rsplit('/', 1)[-1]}")
        return False

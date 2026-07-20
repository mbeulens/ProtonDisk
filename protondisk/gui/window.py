"""Main application window (GTK4 + libadwaita)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GObject  # noqa: E402

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
        self._upload_btn = Gtk.Button(icon_name="document-send-symbolic")
        self._download_btn = Gtk.Button(icon_name="folder-download-symbolic")
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

        self._status = Gtk.Label(xalign=0, margin_start=8, margin_end=8,
                                 margin_top=4, margin_bottom=4)
        self._status.add_css_class("dim-label")
        self._toolbar.add_bottom_bar(self._status)

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
        self._stack.set_visible_child_name("browser" if self._store.get_n_items() else "signed_out")
        return False

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
        self._reload(self._nav.refresh)
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

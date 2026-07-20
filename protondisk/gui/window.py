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

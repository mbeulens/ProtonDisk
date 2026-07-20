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

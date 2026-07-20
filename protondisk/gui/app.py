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

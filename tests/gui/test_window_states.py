import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry, AuthStatus


class FakeDisk:
    def auth_status(self):
        return AuthStatus(logged_in=True, account="test@proton.me")

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

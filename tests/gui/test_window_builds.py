import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import AuthStatus


class _FakeDisk:
    """Minimal disk double: MainWindow probes auth on construction."""

    def auth_status(self):
        return AuthStatus(logged_in=False, account=None)

    def list(self, path):
        return []


def test_main_window_is_a_widget_and_holds_disk():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    disk = _FakeDisk()
    win = MainWindow(application=app, disk=disk)
    assert isinstance(win, Gtk.Widget)
    assert win._disk is disk
    assert win.get_title() == "ProtonDisk"

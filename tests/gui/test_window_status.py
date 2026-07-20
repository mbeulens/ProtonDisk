import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.gui.format import human_size
from protondisk.core.models import AuthStatus


class FakeDisk:
    def list(self, path):
        return []

    def auth_status(self):
        return AuthStatus(logged_in=False, account=None)


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

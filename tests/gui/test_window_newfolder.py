import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import AuthStatus


class FakeDisk:
    def auth_status(self):
        return AuthStatus(logged_in=True, account="u@pm.me")

    def list(self, path):
        return []


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_valid_new_name():
    assert MainWindow._valid_new_name("", []) is not None
    assert MainWindow._valid_new_name("a/b", []) is not None
    assert MainWindow._valid_new_name("Reports", ["Reports"]) is not None
    assert MainWindow._valid_new_name("New", ["Reports"]) is None

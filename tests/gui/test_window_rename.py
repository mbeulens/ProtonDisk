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


def test_rename_is_noop():
    assert MainWindow._rename_is_noop("a.txt", "a.txt") is True
    assert MainWindow._rename_is_noop("a.txt", "") is True
    assert MainWindow._rename_is_noop("a.txt", "b.txt") is False

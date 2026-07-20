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


def test_can_paste_into():
    assert MainWindow._can_paste_into("", "/my-files") is False
    assert MainWindow._can_paste_into("/my-files/a.txt", "/my-files") is False   # same parent
    assert MainWindow._can_paste_into("/my-files/Dir", "/my-files/Dir") is False # into itself
    assert MainWindow._can_paste_into("/my-files/Dir", "/my-files/Dir/sub") is False
    assert MainWindow._can_paste_into("/my-files/a.txt", "/my-files/Reports") is True

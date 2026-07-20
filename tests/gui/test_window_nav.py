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
        return [Entry("Reports", "/my-files/Reports", True, None, None, "u1")]


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_breadcrumb_labels_follow_navigation():
    win = _win()
    assert win._breadcrumb_labels() == ["my-files"]
    win._nav.navigate_to("/my-files/Reports")
    assert win._breadcrumb_labels() == ["my-files", "Reports"]


def test_nav_button_states_reflect_history():
    win = _win()
    assert win._nav_button_states() == (False, False)
    win._nav.navigate_to("/my-files/Reports")
    assert win._nav_button_states() == (True, False)
    win._nav.go_back()
    assert win._nav_button_states() == (False, True)

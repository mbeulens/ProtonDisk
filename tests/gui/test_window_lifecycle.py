import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry, AuthStatus
from protondisk.core.errors import AuthError


class FakeDisk:
    def auth_status(self):
        return AuthStatus(logged_in=True, account="u@pm.me")
    def list(self, path):
        return [Entry("a.txt", "/my-files/a.txt", False, 10, None, "u")]


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_error_restores_view_not_stuck_on_loading():
    win = _win()
    win._stack.set_visible_child_name("loading")
    win._on_error(AuthError("boom"))
    assert win._stack.get_visible_child_name() != "loading"


def test_stale_load_result_is_dropped():
    win = _win()
    win._store.remove_all()
    win._load_gen = 5
    entries = [Entry("ghost.txt", "/my-files/ghost.txt", False, 1, None, "g")]
    win._on_entries_loaded(entries, gen=3)          # stale
    assert win._store.get_n_items() == 0            # dropped, store untouched
    win._on_entries_loaded(entries, gen=5)          # current
    assert win._store.get_n_items() == 1


def test_entries_use_core_provided_path():
    win = _win()
    win._load_gen = 1
    entries = [Entry("a.txt", "/my-files/Reports/a.txt", False, 1, None, "u")]
    win._on_entries_loaded(entries, gen=1)
    assert win._store.get_item(0).path == "/my-files/Reports/a.txt"

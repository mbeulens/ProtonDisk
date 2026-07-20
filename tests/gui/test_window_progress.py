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


def test_activity_text():
    win = _win()
    assert win._activity_text("upload", "a.txt") == "Uploading a.txt…"
    assert win._activity_text("download", "a.txt") == "Downloading a.txt…"


def test_begin_end_activity_toggles_spinner():
    win = _win()
    assert win._spinner.get_visible() is False
    win._begin_activity("Uploading a.txt…")
    assert win._spinner.get_visible() is True
    assert win._status.get_label() == "Uploading a.txt…"
    win._end_activity()
    assert win._spinner.get_visible() is False


def test_concurrent_activities_keep_spinner_until_all_done():
    win = _win()
    win._begin_activity("Uploading a…")
    win._begin_activity("Uploading b…")
    win._end_activity()
    assert win._spinner.get_visible() is True     # one still running
    win._end_activity()
    assert win._spinner.get_visible() is False


def test_set_activity_phase_updates_label_during_transfer():
    win = _win()
    win._begin_activity("Uploading a.txt…")
    win._set_activity_phase("a.txt", "Encrypting…")
    assert win._status.get_label() == "Encrypting… a.txt"
    win._end_activity()


def test_phase_ignored_when_no_active_transfer():
    win = _win()
    win._status.set_label("3 items · u@pm.me")
    win._set_activity_phase("a.txt", "Encrypting…")   # nothing in flight
    assert win._status.get_label() == "3 items · u@pm.me"

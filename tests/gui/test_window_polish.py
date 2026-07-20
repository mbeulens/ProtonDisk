import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import AuthStatus, TransferResult


class FakeDisk:
    def auth_status(self):
        return AuthStatus(logged_in=True, account="u@pm.me")

    def list(self, path):
        return []


def _win():
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=FakeDisk())


def test_recovery_view_signed_in_empty_folder_stays_browser():
    win = _win()
    win._account = "u@pm.me"
    win._store.remove_all()
    assert win._recovery_view() == "browser"


def test_recovery_view_logged_out_goes_signed_out():
    win = _win()
    win._account = None
    win._store.remove_all()
    assert win._recovery_view() == "signed_out"


def test_upload_result_message_distinguishes_skip_from_upload():
    uploaded = TransferResult(1, 10, 0, 0, [])
    skipped = TransferResult(0, 0, 1, 0, [])
    assert MainWindow._upload_result_message("a.txt", uploaded) == "Uploaded a.txt"
    assert MainWindow._upload_result_message("a.txt", skipped) == "Skipped a.txt (already exists)"
    assert MainWindow._upload_result_message("a.txt", None) == "Uploaded a.txt"

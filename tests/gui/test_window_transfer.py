import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from protondisk.gui.window import MainWindow
from protondisk.core.models import Entry, TransferResult, AuthStatus


class FakeDisk:
    def __init__(self):
        self.uploads = []
        self.downloads = []

    def auth_status(self):
        return AuthStatus(logged_in=True, account="u@pm.me")

    def list(self, path):
        return [Entry("a.txt", "/my-files/a.txt", False, 10, None, "u2")]

    def upload(self, local, parent, *, conflict="skip"):
        self.uploads.append((local, parent, conflict))
        return TransferResult(1, 10, 0, 0, [])

    def download(self, remote, folder):
        self.downloads.append((remote, folder))
        return TransferResult(1, 10, 0, 0, [])


def _win(disk):
    Adw.init()
    app = Adw.Application(application_id="dev.protondisk.Test")
    return MainWindow(application=app, disk=disk)


def test_can_download_only_for_files():
    win = _win(FakeDisk())
    assert win._can_download(False) is True     # a file
    assert win._can_download(True) is False      # a folder
    assert win._can_download(None) is False      # nothing selected


def test_upload_one_calls_core_with_current_parent():
    disk = FakeDisk()
    win = _win(disk)
    win._nav.navigate_to("/my-files/Reports")
    win._upload_one("/tmp/local.txt")
    assert disk.uploads == [("/tmp/local.txt", "/my-files/Reports", "skip")]


def test_download_one_calls_core():
    disk = FakeDisk()
    win = _win(disk)
    win._download_one("/my-files/a.txt", "/tmp/out")
    assert disk.downloads == [("/my-files/a.txt", "/tmp/out")]

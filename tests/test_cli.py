import protondisk
from protondisk.cli import main
from protondisk.core.models import AuthStatus, Entry
from protondisk.core.errors import AuthError


class FakeDisk:
    def __init__(self, *, status=None, entries=None, error=None):
        self._status = status
        self._entries = entries or []
        self._error = error

    def auth_status(self):
        if self._error:
            raise self._error
        return self._status

    def list(self, path):
        if self._error:
            raise self._error
        return self._entries


def test_version_prints_version(capsys):
    assert main(["version"]) == 0
    assert protondisk.__version__ in capsys.readouterr().out


def test_auth_status_prints_account(capsys):
    disk = FakeDisk(status=AuthStatus(logged_in=True, account="user@pm.me"))
    assert main(["auth-status"], disk=disk) == 0
    assert "user@pm.me" in capsys.readouterr().out


def test_ls_lists_entries(capsys):
    disk = FakeDisk(entries=[
        Entry("Reports", "/my-files/Reports", True, None, None, "U1"),
        Entry("q3.pdf", "/my-files/q3.pdf", False, 10, None, "U2"),
    ])
    assert main(["ls", "/my-files"], disk=disk) == 0
    out = capsys.readouterr().out
    assert "Reports" in out and "q3.pdf" in out


def test_error_returns_1_and_prints_stderr(capsys):
    disk = FakeDisk(error=AuthError("not logged in"))
    assert main(["auth-status"], disk=disk) == 1
    assert "not logged in" in capsys.readouterr().err


def test_missing_binary_prints_error_not_traceback(capsys, monkeypatch):
    from protondisk.core.errors import CLINotFoundError
    def boom():
        raise CLINotFoundError("Could not find the 'proton-drive' binary on PATH.")
    monkeypatch.setattr("protondisk.cli.ProtonDisk", boom)
    rc = main(["auth-status"])  # no injected disk -> constructs ProtonDisk() -> raises
    assert rc == 1
    assert "proton-drive" in capsys.readouterr().err

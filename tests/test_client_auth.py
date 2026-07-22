from protondisk.core.client import ProtonDisk
from protondisk.core.models import AuthStatus
from protondisk.core.errors import AuthError


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        if not self._results:
            return {}
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_auth_status_logged_in_reads_account_from_ownedBy():
    runner = FakeRunner([{"type": "folder", "ownedBy": {"email": "user@pm.me"}}])
    status = ProtonDisk(runner=runner).auth_status()
    assert status == AuthStatus(logged_in=True, account="user@pm.me")
    assert runner.calls[0] == ("filesystem", "info", "/my-files")


def test_auth_status_logged_out_on_auth_error():
    runner = FakeRunner([AuthError("You need to login first")])
    status = ProtonDisk(runner=runner).auth_status()
    assert status == AuthStatus(logged_in=False, account=None)


def test_login_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).login()
    assert runner.calls[0] == ("auth", "login")


def test_logout_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).logout()
    assert runner.calls[0] == ("auth", "logout")

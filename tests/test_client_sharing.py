from protondisk.core import ProtonDisk, ShareInfo, AuthError  # exercises re-exports


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_sharing_status_unshared_returns_not_shared():
    runner = FakeRunner([{}])  # runner maps `undefined` -> {}
    info = ProtonDisk(runner=runner).sharing_status("/my-files/kaas.txt")
    assert isinstance(info, ShareInfo)
    assert info.shared is False and info.members == []
    assert runner.calls[0] == ("sharing", "status", "/my-files/kaas.txt")


def test_sharing_invite_with_message_passes_all_flags():
    runner = FakeRunner()
    ProtonDisk(runner=runner).sharing_invite(
        "/my-files/Reports", "b@pm.me", role="editor", message="pls review")
    assert runner.calls[0] == (
        "sharing", "invite", "--user", "b@pm.me", "--role", "editor",
        "--message", "pls review", "/my-files/Reports")


def test_sharing_invite_omits_empty_message_and_defaults_viewer():
    runner = FakeRunner()
    ProtonDisk(runner=runner).sharing_invite("/my-files/Reports", "b@pm.me")
    assert runner.calls[0] == (
        "sharing", "invite", "--user", "b@pm.me", "--role", "viewer",
        "/my-files/Reports")


def test_error_is_reexported():
    assert issubclass(AuthError, Exception)

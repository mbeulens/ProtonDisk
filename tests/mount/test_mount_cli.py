from protondisk.cli import _cmd_mount, _cmd_unmount
from protondisk.core.models import AuthStatus


class FakeDisk:
    def __init__(self, logged_in=True):
        self._st = AuthStatus(logged_in=logged_in, account="u@pm.me")
    def auth_status(self):
        return self._st


class FakeMounter:
    def __init__(self, unmount_ok=True):
        self.mounted = None
        self.unmounted = None
        self._unmount_ok = unmount_ok
    def mount(self, disk, mountpoint, *, ttl=5.0, foreground=True):
        self.mounted = mountpoint
    def unmount(self, mountpoint):
        self.unmounted = mountpoint
        return self._unmount_ok


def test_mount_requires_auth(capsys):
    m = FakeMounter()
    rc = _cmd_mount(FakeDisk(logged_in=False), "/tmp/mp", mounter=m)
    assert rc == 1
    assert "sign" in capsys.readouterr().err.lower()
    assert m.mounted is None            # never mounted while logged out


def test_mount_when_authed_calls_mounter(capsys):
    m = FakeMounter()
    rc = _cmd_mount(FakeDisk(logged_in=True), "/tmp/mp", mounter=m)
    assert rc == 0
    assert m.mounted == "/tmp/mp"
    assert "/tmp/mp" in capsys.readouterr().out


def test_mount_message_mentions_read_write(capsys):
    from protondisk.cli import _cmd_mount
    from protondisk.core.models import AuthStatus

    class D:
        def auth_status(self): return AuthStatus(True, "u@pm.me")
    class M:
        def mount(self, disk, mountpoint, *, ttl=5.0, foreground=True): pass
        def unmount(self, mp): return True
    _cmd_mount(D(), "/tmp/mp", mounter=M())
    assert "read-write" in capsys.readouterr().out.lower()


def test_unmount_success_and_failure():
    ok = FakeMounter(unmount_ok=True)
    assert _cmd_unmount("/tmp/mp", mounter=ok) == 0 and ok.unmounted == "/tmp/mp"
    bad = FakeMounter(unmount_ok=False)
    assert _cmd_unmount("/tmp/mp", mounter=bad) == 1

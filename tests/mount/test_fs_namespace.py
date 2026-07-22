import errno
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self):
        self.calls = []
        self._tree = {
            "/my-files": [
                Entry("a.txt", "/my-files/a.txt", False, 5, 1.0, "f"),
                Entry("Dir", "/my-files/Dir", True, None, 1.0, "d"),
                Entry("b.txt", "/my-files/b.txt", False, 3, 1.0, "g"),
            ],
            "/my-files/Dir": [],
        }
    def list(self, path):
        return self._tree.get(path, [])
    def mkdir(self, path):
        self.calls.append(("mkdir", path))
    def trash(self, path):
        self.calls.append(("trash", path))
    def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
    def move(self, src, target_parent):
        self.calls.append(("move", src, target_parent))


def test_mkdir_calls_core():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    assert fs.mkdir("/NewDir", 0o755) == 0
    assert ("mkdir", "/my-files/NewDir") in disk.calls


def test_unlink_and_rmdir_trash():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.unlink("/a.txt"); fs.rmdir("/Dir")
    assert ("trash", "/my-files/a.txt") in disk.calls
    assert ("trash", "/my-files/Dir") in disk.calls


def test_rename_same_dir():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.rename("/a.txt", "/renamed.txt")
    assert ("rename", "/my-files/a.txt", "renamed.txt") in disk.calls


def test_rename_into_other_dir_uses_move():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    fs.rename("/a.txt", "/Dir/a.txt")
    assert ("move", "/my-files/a.txt", "/my-files/Dir") in disk.calls


def test_rename_onto_existing_trashes_then_renames():
    # Atomic-rename saves: replacing an existing name trashes the old file first
    # (recoverable) then renames onto it — in that order.
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    assert fs.rename("/a.txt", "/b.txt") == 0     # b.txt already exists
    assert disk.calls == [
        ("trash", "/my-files/b.txt"),
        ("rename", "/my-files/a.txt", "b.txt"),
    ]


def test_rename_onto_existing_retries_until_the_trash_settles(monkeypatch):
    # The rename onto a just-trashed name can momentarily still collide; retry.
    slept = []
    monkeypatch.setattr("protondisk.mount.fs.time.sleep", lambda s: slept.append(s))

    class FlakyDisk(FakeDisk):
        def __init__(self):
            super().__init__()
            self._rename_fails = 2       # first two rename attempts collide
        def rename(self, path, new_name):
            self.calls.append(("rename", path, new_name))
            if self._rename_fails > 0:
                self._rename_fails -= 1
                raise NotFoundError("still exists (eventual consistency)")

    disk = FlakyDisk(); fs = ProtonDiskFS(disk)
    assert fs.rename("/a.txt", "/b.txt") == 0
    assert [c for c in disk.calls if c[0] == "rename"].__len__() == 3   # 2 fails + 1 ok
    assert slept == [0.5, 0.5]           # slept between the failed attempts


def test_rename_onto_existing_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr("protondisk.mount.fs.time.sleep", lambda s: None)

    class AlwaysCollides(FakeDisk):
        def rename(self, path, new_name):
            self.calls.append(("rename", path, new_name))
            raise NotFoundError("persistent collision")

    disk = AlwaysCollides(); fs = ProtonDiskFS(disk)
    with pytest.raises(FuseOSError) as ei:
        fs.rename("/a.txt", "/b.txt")
    assert ei.value.errno == errno.EIO
    assert disk.calls[0] == ("trash", "/my-files/b.txt")   # target still got trashed


def test_core_error_maps_to_eio():
    class BadDisk(FakeDisk):
        def trash(self, path):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.unlink("/a.txt")
    assert ei.value.errno == errno.EIO


def test_rename_onto_itself_is_noop_not_eexist():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    assert fs.rename("/a.txt", "/a.txt") == 0        # self-rename: no-op
    assert all(c[0] not in ("rename", "move") for c in disk.calls)


def test_cross_parent_move_blocked_when_source_name_exists_in_target():
    disk = FakeDisk()
    # Dir already contains an "a.txt"
    disk._tree["/my-files/Dir"] = [Entry("a.txt", "/my-files/Dir/a.txt", False, 1, 1.0, "x")]
    fs = ProtonDiskFS(disk)
    with pytest.raises(FuseOSError) as ei:
        fs.rename("/a.txt", "/Dir/renamed.txt")   # move lands a.txt in Dir first -> collision
    assert ei.value.errno == errno.EEXIST
    assert all(c[0] not in ("move", "rename") for c in disk.calls)

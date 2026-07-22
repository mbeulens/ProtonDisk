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


def test_rename_onto_existing_name_is_eexist():
    disk = FakeDisk(); fs = ProtonDiskFS(disk)
    with pytest.raises(FuseOSError) as ei:
        fs.rename("/a.txt", "/b.txt")     # b.txt already exists
    assert ei.value.errno == errno.EEXIST
    assert all(c[0] != "rename" for c in disk.calls)  # nothing attempted


def test_core_error_maps_to_eio():
    class BadDisk(FakeDisk):
        def trash(self, path):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.unlink("/a.txt")
    assert ei.value.errno == errno.EIO

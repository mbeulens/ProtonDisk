import errno
import stat as stat_mod
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry


class FakeDisk:
    def __init__(self):
        self.list_calls = []
        self._tree = {
            "/my-files": [
                Entry("Reports", "/my-files/Reports", True, None, 1720000000.0, "d"),
                Entry("a.txt", "/my-files/a.txt", False, 95, 1720000001.0, "f"),
            ],
            "/my-files/Reports": [
                Entry("q3.pdf", "/my-files/Reports/q3.pdf", False, 10, 1720000002.0, "g"),
            ],
        }

    def list(self, path):
        self.list_calls.append(path)
        return self._tree.get(path, [])


def test_readdir_root():
    fs = ProtonDiskFS(FakeDisk())
    assert set(fs.readdir("/", None)) == {".", "..", "Reports", "a.txt"}


def test_getattr_root_is_dir():
    fs = ProtonDiskFS(FakeDisk())
    st = fs.getattr("/")
    assert st["st_mode"] == (stat_mod.S_IFDIR | 0o555)


def test_getattr_file_from_parent_listing_is_one_list_call():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    st = fs.getattr("/a.txt")
    assert st["st_mode"] == (stat_mod.S_IFREG | 0o444)
    assert st["st_size"] == 95
    # getattr of two entries in the same dir must not multiply list() calls (cache)
    fs.getattr("/Reports")
    assert disk.list_calls.count("/my-files") == 1


def test_getattr_missing_raises_enoent():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.getattr("/nope.txt")
    assert ei.value.errno == errno.ENOENT


def test_readonly_ops_raise_erofs():
    fs = ProtonDiskFS(FakeDisk())
    for call in (lambda: fs.mkdir("/x", 0o755),
                 lambda: fs.unlink("/a.txt"),
                 lambda: fs.rename("/a.txt", "/b.txt"),
                 lambda: fs.write("/a.txt", b"x", 0, 1),
                 lambda: fs.create("/x", 0o644)):
        with pytest.raises(FuseOSError) as ei:
            call()
        assert ei.value.errno == errno.EROFS


def test_listing_error_maps_to_eio():
    # A Drive/network error during list must surface as EIO, not a raw exception.
    import errno as _errno
    from protondisk.core.errors import RateLimitError

    class ThrottledDisk:
        def list(self, path):
            raise RateLimitError("Too many requests")

    fs = ProtonDiskFS(ThrottledDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.readdir("/", None)
    assert ei.value.errno == _errno.EIO

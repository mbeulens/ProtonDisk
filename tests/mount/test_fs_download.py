import errno, os
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self, contents=b"hello proton"):
        self._contents = contents
        self.downloads = []
        self._tree = {"/my-files": [
            Entry("a.txt", "/my-files/a.txt", False, len(contents), 1.0, "f"),
            Entry("Dir", "/my-files/Dir", True, None, 1.0, "d"),
        ]}

    def list(self, path):
        return self._tree.get(path, [])

    def download(self, remote, folder):
        self.downloads.append((remote, folder))
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(self._contents)


def test_open_read_release_round_trip():
    disk = FakeDisk(b"hello proton")
    fs = ProtonDiskFS(disk)
    fh = fs.open("/a.txt", os.O_RDONLY)
    assert disk.downloads == [("/my-files/a.txt", fs._open_files[fh][0])]
    assert fs.read("/a.txt", 5, 0, fh) == b"hello"
    assert fs.read("/a.txt", 100, 6, fh) == b"proton"
    tmpdir = fs._open_files[fh][0]
    fs.release("/a.txt", fh)
    assert fh not in fs._open_files
    assert not os.path.exists(tmpdir)   # temp cleaned up


def test_open_write_flag_is_erofs():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/a.txt", os.O_WRONLY)
    assert ei.value.errno == errno.EROFS


def test_open_directory_is_eisdir():
    fs = ProtonDiskFS(FakeDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/Dir", os.O_RDONLY)
    assert ei.value.errno == errno.EISDIR


def test_open_download_failure_is_eio():
    class BadDisk(FakeDisk):
        def download(self, remote, folder):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk())
    with pytest.raises(FuseOSError) as ei:
        fs.open("/a.txt", os.O_RDONLY)
    assert ei.value.errno == errno.EIO

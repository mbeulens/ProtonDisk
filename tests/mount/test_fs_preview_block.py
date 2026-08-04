import errno
import os

import pytest
from fuse import FuseOSError

from protondisk.mount import fs as fs_mod
from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry


class FakeDisk:
    def __init__(self):
        self.downloads = []
        self.list_calls = []
        self._tree = {"/my-files": [Entry("photo.jpg", "/my-files/photo.jpg",
                                          False, 9, 1.0, "f")]}

    def list(self, path):
        self.list_calls.append(path)
        return self._tree.get(path, [])

    def download(self, remote, folder, progress=None):
        self.downloads.append(remote)
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"jpegbytes")

    def upload(self, local, parent, conflict="skip", progress=None):
        return None


def _caller(monkeypatch, pid):
    monkeypatch.setattr(fs_mod, "fuse_get_context", lambda: (1000, 1000, pid))


def _as_preview(monkeypatch, preview_pids):
    monkeypatch.setattr(fs_mod, "is_preview_process", lambda pid: pid in preview_pids)


def test_thumbnailer_read_is_refused_without_downloading(monkeypatch):
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    _caller(monkeypatch, 42)
    _as_preview(monkeypatch, {42})
    with pytest.raises(FuseOSError) as ei:
        fs.open("/photo.jpg", os.O_RDONLY)
    assert ei.value.errno == errno.EACCES
    assert disk.downloads == []      # the point: nothing fetched over the network
    assert disk.list_calls == []     # not even a metadata round-trip


def test_ordinary_reader_still_downloads(monkeypatch):
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    _caller(monkeypatch, 7)
    _as_preview(monkeypatch, {42})
    fh = fs.open("/photo.jpg", os.O_RDONLY)
    assert fs.read("/photo.jpg", 9, 0, fh) == b"jpegbytes"
    fs.release("/photo.jpg", fh)
    assert disk.downloads == ["/my-files/photo.jpg"]


def test_preview_block_can_be_disabled(monkeypatch):
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, block_previews=False)
    _caller(monkeypatch, 42)
    _as_preview(monkeypatch, {42})
    fh = fs.open("/photo.jpg", os.O_RDONLY)
    fs.release("/photo.jpg", fh)
    assert disk.downloads == ["/my-files/photo.jpg"]


def test_write_open_from_preview_caller_is_not_blocked(monkeypatch):
    # only content reads are refused; a write path would never come from a
    # thumbnailer, and blocking it could lose data
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    _caller(monkeypatch, 42)
    _as_preview(monkeypatch, {42})
    fh = fs.open("/new.txt", os.O_WRONLY | os.O_CREAT)
    fs.write("/new.txt", b"hi", 0, fh)
    fs.release("/new.txt", fh)


def test_missing_caller_context_allows_the_read(monkeypatch):
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    monkeypatch.setattr(fs_mod, "fuse_get_context", lambda: (_ for _ in ()).throw(RuntimeError))
    fh = fs.open("/photo.jpg", os.O_RDONLY)
    fs.release("/photo.jpg", fh)
    assert disk.downloads == ["/my-files/photo.jpg"]


def test_metadata_ops_are_unaffected_for_preview_callers(monkeypatch):
    # listing and stat stay cheap and allowed, so the folder still shows its files
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    _caller(monkeypatch, 42)
    _as_preview(monkeypatch, {42})
    assert "photo.jpg" in fs.readdir("/", None)
    assert fs.getattr("/photo.jpg")["st_size"] == 9

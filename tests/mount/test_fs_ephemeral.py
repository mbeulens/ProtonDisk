import errno, os
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry, TransferResult


class FakeDisk:
    def __init__(self):
        self.uploads = []
        self.trashes = []
        self._tree = {"/my-files": [Entry("real.txt", "/my-files/real.txt", False, 3, 1.0, "r")]}

    def list(self, path):
        return self._tree.get(path, [])

    def upload(self, local, parent, *, conflict="skip", progress=None):
        with open(local, "rb") as f:
            data = f.read()
        self.uploads.append((os.path.basename(local), parent, conflict, data))
        return TransferResult(1, len(data), 0, 0, [])

    def trash(self, path):
        self.trashes.append(path)

    def download(self, remote, folder, progress=None):
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"REAL")


def _fs():
    return ProtonDiskFS(FakeDisk())


def test_swap_file_is_never_uploaded():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    fh = fs.create("/.notes.txt.swp", 0o600)
    fs.write("/.notes.txt.swp", b"vim swap data", 0, fh)
    fs.release("/.notes.txt.swp", fh)
    assert disk.uploads == []          # nothing uploaded to the Drive
    # ...but it's readable within the mount (local-only)
    assert fs.getattr("/.notes.txt.swp")["st_size"] == len(b"vim swap data")


def test_swap_file_read_write_roundtrip_local():
    fs = _fs()
    fh = fs.create("/.x.swp", 0o600)
    fs.write("/.x.swp", b"hello", 0, fh)
    assert fs.read("/.x.swp", 5, 0, fh) == b"hello"
    fs.release("/.x.swp", fh)


def test_swap_shows_in_readdir_but_not_uploaded_and_unlink_is_local():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    fh = fs.create("/.a.swp", 0o600); fs.release("/.a.swp", fh)
    names = fs.readdir("/", None)
    assert ".a.swp" in names and "real.txt" in names   # local temp + real file both visible
    fs.unlink("/.a.swp")
    assert disk.trashes == []                            # not trashed on the Drive (local-only)
    with pytest.raises(FuseOSError) as ei:
        fs.getattr("/.a.swp")
    assert ei.value.errno == errno.ENOENT


def test_getattr_missing_ephemeral_is_enoent_without_touching_drive():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    with pytest.raises(FuseOSError) as ei:
        fs.getattr("/.never.swp")
    assert ei.value.errno == errno.ENOENT


def test_atomic_save_via_goutputstream_uploads_to_the_real_target():
    # GNOME/gio: write .goutputstream-XXXX (local-only), then rename onto the real
    # file. The bridge uploads the temp's content to the destination; the temp
    # itself never lands on the Drive.
    disk = FakeDisk()
    fs = ProtonDiskFS(disk)
    fh = fs.create("/.goutputstream-ABC123", 0o644)
    fs.write("/.goutputstream-ABC123", b"the new document", 0, fh)
    fs.release("/.goutputstream-ABC123", fh)
    assert disk.uploads == []                           # temp not uploaded yet
    fs.rename("/.goutputstream-ABC123", "/real.txt")    # atomic-save completion
    assert len(disk.uploads) == 1
    name, parent, conflict, data = disk.uploads[0]
    assert name == "real.txt" and parent == "/my-files"
    assert conflict == "replace" and data == b"the new document"
    # the local temp is gone
    with pytest.raises(FuseOSError):
        fs.getattr("/.goutputstream-ABC123")


def test_chmod_on_ephemeral_is_noop_but_erofs_on_real():
    fs = _fs()
    fh = fs.create("/.y.swp", 0o600); fs.release("/.y.swp", fh)
    assert fs.chmod("/.y.swp", 0o644) == 0        # local temp: accepted
    with pytest.raises(FuseOSError) as ei:
        fs.chmod("/real.txt", 0o644)              # real file: read-only attr
    assert ei.value.errno == errno.EROFS

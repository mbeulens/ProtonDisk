import errno, os, stat as stat_mod
import pytest
from fuse import FuseOSError

from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry, TransferResult
from protondisk.core.errors import NotFoundError


class FakeDisk:
    def __init__(self):
        self.uploads = []          # (local_bytes, parent, conflict)
        self._tree = {"/my-files": [Entry("Dir", "/my-files/Dir", True, None, 1.0, "d")]}
    def list(self, path):
        return self._tree.get(path, [])
    def download(self, remote, folder, progress=None):
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"existing")
    def upload(self, local, parent, *, conflict="skip", progress=None):
        with open(local, "rb") as f:
            data = f.read()
        self.uploads.append((data, parent, conflict, os.path.basename(local)))
        if progress:
            progress("Encrypting…"); progress("Uploading…")
        return TransferResult(1, len(data), 0, 0, [])


class FakeNotifier:
    def __init__(self): self.events = []
    def begin(self, body=""): self.events.append(("begin", body)); return {"h": 1}
    def update(self, h, body): self.events.append(("update", body))
    def finish(self, h, body, timeout_ms=3000): self.events.append(("finish", body))


def _fs():
    return ProtonDiskFS(FakeDisk(), notifier=FakeNotifier())


def test_create_write_release_uploads_replace_under_basename():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/new.txt", 0o644)
    assert fs.write("/new.txt", b"hello ", 0, fh) == 6
    assert fs.write("/new.txt", b"world", 6, fh) == 5
    fs.release("/new.txt", fh)
    assert len(disk.uploads) == 1
    data, parent, conflict, name = disk.uploads[0]
    assert data == b"hello world"
    assert parent == "/my-files" and conflict == "replace" and name == "new.txt"


def test_getattr_reports_buffer_size_for_open_write_handle():
    fs = _fs()
    fh = fs.create("/new.txt", 0o644)
    fs.write("/new.txt", b"1234", 0, fh)
    st = fs.getattr("/new.txt")           # not in the listing yet -> served from handle
    assert st["st_size"] == 4
    assert stat_mod.S_ISREG(st["st_mode"])
    fs.release("/new.txt", fh)


def test_flush_uploads_and_clears_dirty_then_release_is_noop():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/f.txt", 0o644)
    fs.write("/f.txt", b"abc", 0, fh)
    fs.flush("/f.txt", fh)
    fs.release("/f.txt", fh)
    assert len(disk.uploads) == 1         # not re-uploaded on release


def test_truncate_via_handle_changes_uploaded_size():
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=FakeNotifier())
    fh = fs.create("/t.txt", 0o644)
    fs.write("/t.txt", b"abcdef", 0, fh)
    fs.truncate("/t.txt", 3, fh)
    fs.release("/t.txt", fh)
    assert disk.uploads[0][0] == b"abc"


def test_upload_error_maps_to_eio():
    class BadDisk(FakeDisk):
        def upload(self, local, parent, *, conflict="skip", progress=None):
            raise NotFoundError("gone")
    fs = ProtonDiskFS(BadDisk(), notifier=FakeNotifier())
    fh = fs.create("/x.txt", 0o644)
    fs.write("/x.txt", b"z", 0, fh)
    with pytest.raises(FuseOSError) as ei:
        fs.flush("/x.txt", fh)
    assert ei.value.errno == errno.EIO
    fs.release("/x.txt", fh)              # cleanup still succeeds


def test_upload_notification_phases():
    note = FakeNotifier()
    disk = FakeDisk()
    fs = ProtonDiskFS(disk, notifier=note)
    fh = fs.create("/n.txt", 0o644)
    fs.write("/n.txt", b"q", 0, fh)
    fs.release("/n.txt", fh)
    assert note.events[0][0] == "begin"
    assert ("update", "Encrypting… n.txt") in note.events
    assert ("update", "Uploading… n.txt") in note.events
    assert note.events[-1][0] == "finish"

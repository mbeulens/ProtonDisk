import os
from protondisk.mount.fs import ProtonDiskFS
from protondisk.core.models import Entry


class FakeDisk:
    def __init__(self):
        self._tree = {"/my-files": [Entry("a.txt", "/my-files/a.txt", False, 5, 1.0, "f")]}
    def list(self, path):
        return self._tree.get(path, [])
    def download(self, remote, folder, progress=None):
        if progress:
            progress("Downloading…")
            progress("Decrypting…")
        with open(os.path.join(folder, os.path.basename(remote)), "wb") as f:
            f.write(b"hello")


class FakeNotifier:
    def __init__(self):
        self.events = []          # ("begin"|"update"|"finish"|"fail", body)
        self.quiet = []           # whether each begin() asked to stay quiet
    def begin(self, body="", quiet=False):
        self.events.append(("begin", body)); self.quiet.append(quiet); return {"h": 1}
    def update(self, handle, body):
        self.events.append(("update", body))
    def finish(self, handle, body, timeout_ms=3000):
        self.events.append(("finish", body))
    def fail(self, handle, body, timeout_ms=5000):
        self.events.append(("fail", body))


def test_read_open_emits_download_phases_to_notifier():
    note = FakeNotifier()
    fs = ProtonDiskFS(FakeDisk(), notifier=note)
    fh = fs.open("/a.txt", os.O_RDONLY)
    assert fs.read("/a.txt", 5, 0, fh) == b"hello"
    fs.release("/a.txt", fh)
    kinds = [k for k, _ in note.events]
    assert kinds[0] == "begin"
    assert ("update", "Downloading… a.txt") in note.events
    assert ("update", "Decrypting… a.txt") in note.events
    assert kinds[-1] == "finish"


def test_read_download_is_announced_quietly():
    # a read is usually the desktop peeking at a file; only a slow one may pop up
    note = FakeNotifier()
    fs = ProtonDiskFS(FakeDisk(), notifier=note)
    fs.release("/a.txt", fs.open("/a.txt", os.O_RDONLY))
    assert note.quiet == [True]


def test_readdir_emits_no_notifications():
    note = FakeNotifier()
    fs = ProtonDiskFS(FakeDisk(), notifier=note)
    fs.readdir("/", None)
    fs.getattr("/a.txt")
    assert note.events == []       # metadata ops are silent

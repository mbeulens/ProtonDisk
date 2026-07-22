from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_mkdir_splits_parent_and_name():
    runner = FakeRunner([{"uid": "U", "name": {"ok": True, "value": "New"}, "type": "folder"}])
    ProtonDisk(runner=runner).mkdir("/my-files/New")
    assert runner.calls[0] == ("filesystem", "create-folder", "/my-files", "New")


def test_rename_invokes_cli():
    runner = FakeRunner([{"uid": "U", "name": {"ok": True, "value": "b.txt"}, "type": "file"}])
    ProtonDisk(runner=runner).rename("/my-files/a.txt", "b.txt")
    assert runner.calls[0] == ("filesystem", "rename", "/my-files/a.txt", "b.txt")


def test_move_targets_parent_folder():
    runner = FakeRunner([[{"uid": "U", "ok": True}]])
    ProtonDisk(runner=runner).move("/my-files/a.txt", "/my-files/Folder")
    assert runner.calls[0] == ("filesystem", "move", "/my-files/a.txt", "/my-files/Folder")


def test_trash_invokes_cli():
    runner = FakeRunner([[{"uid": "U", "ok": True}]])
    ProtonDisk(runner=runner).trash("/my-files/old.txt")
    assert runner.calls[0] == ("filesystem", "trash", "/my-files/old.txt")

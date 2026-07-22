from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


LIST_MYFILES = [
    {"uid": "U1", "name": {"ok": True, "value": "kaas.txt"}, "type": "file",
     "totalStorageSize": 95, "modificationTime": "2026-03-26T00:51:13.000Z"},
    {"uid": "U2", "name": {"ok": True, "value": "Test map"}, "type": "folder",
     "modificationTime": "2026-03-26T02:17:11.000Z"},
]


def test_list_parses_array_with_parent_path():
    runner = FakeRunner([LIST_MYFILES])
    entries = ProtonDisk(runner=runner).list("/my-files")
    assert runner.calls[0] == ("filesystem", "list", "/my-files")
    assert [e.name for e in entries] == ["kaas.txt", "Test map"]
    assert entries[0].path == "/my-files/kaas.txt"
    assert entries[0].size == 95
    assert entries[1].is_dir is True


def test_list_sections_from_root():
    runner = FakeRunner([[{"path": "/my-files"}, {"path": "/trash"}]])
    entries = ProtonDisk(runner=runner).list("/")
    assert [e.name for e in entries] == ["my-files", "trash"]
    assert all(e.is_dir for e in entries)


def test_list_non_list_returns_empty():
    assert ProtonDisk(runner=FakeRunner([{}])).list("/my-files") == []


def test_stat_uses_info_and_path_override():
    info = {"uid": "U1", "name": {"ok": True, "value": "kaas.txt"}, "type": "file",
            "totalStorageSize": 95, "modificationTime": "2026-03-26T00:51:13.000Z"}
    runner = FakeRunner([info])
    entry = ProtonDisk(runner=runner).stat("/my-files/kaas.txt")
    assert runner.calls[0] == ("filesystem", "info", "/my-files/kaas.txt")
    assert entry.name == "kaas.txt"
    assert entry.path == "/my-files/kaas.txt"
    assert entry.is_dir is False

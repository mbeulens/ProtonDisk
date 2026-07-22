from protondisk.core.client import ProtonDisk

TRANSFER = {"transferredItems": 1, "transferredBytes": 17,
            "skippedItems": 0, "failedItems": 0, "failures": []}


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_upload_passes_conflict_strategy_and_parses_result():
    runner = FakeRunner([TRANSFER])
    result = ProtonDisk(runner=runner).upload("./a.txt", "/my-files", conflict="replace")
    assert runner.calls[0] == (
        "filesystem", "upload", "--conflict-strategy", "replace", "./a.txt", "/my-files")
    assert result.transferred_items == 1 and result.transferred_bytes == 17


def test_upload_default_conflict_is_skip():
    runner = FakeRunner([TRANSFER])
    ProtonDisk(runner=runner).upload("./a.txt", "/my-files")
    assert runner.calls[0][:4] == (
        "filesystem", "upload", "--conflict-strategy", "skip")


def test_download_parses_result():
    runner = FakeRunner([TRANSFER])
    result = ProtonDisk(runner=runner).download("/my-files/a.txt", "./dl")
    assert runner.calls[0] == ("filesystem", "download", "/my-files/a.txt", "./dl")
    assert result.transferred_bytes == 17

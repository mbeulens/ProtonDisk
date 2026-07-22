"""Tests for progress-callback wiring on upload/download."""
from protondisk.core.client import ProtonDisk
from protondisk.core.models import TransferResult

TRANSFER = {"transferredItems": 1, "transferredBytes": 30,
            "skippedItems": 0, "failedItems": 0, "failures": []}

# Real-shaped verbose lines the fake runner will stream to on_line.
UPLOAD_LINES = [
    "2026 INFO [upload] revision X: Starting upload",
    "2026 DEBUG [upload] revision X: Encrypting block 1",
    '2026 INFO [metric] performance {"type":"content_encryption"}',  # noise -> no phase
    "2026 INFO [upload] revision X: Uploading",
    '{"transferredItems":1,"transferredBytes":30,"skippedItems":0,"failedItems":0,"failures":[]}',
]


class FakeRunner:
    def __init__(self, lines=None, result=None):
        self.calls = []
        self.streaming_calls = []
        self._lines = lines or []
        self._result = result if result is not None else TRANSFER

    def run(self, *args, input_text=None, timeout=None):
        self.calls.append(args)
        return self._result

    def run_streaming(self, *args, on_line=None):
        self.streaming_calls.append(args)
        for line in self._lines:
            if on_line is not None:
                on_line(line)
        return self._result


def test_upload_without_progress_uses_plain_run():
    runner = FakeRunner()
    result = ProtonDisk(runner=runner).upload("./a", "/my-files")
    assert runner.calls[0] == (
        "filesystem", "upload", "--conflict-strategy", "skip", "./a", "/my-files")
    assert runner.streaming_calls == []
    assert isinstance(result, TransferResult) and result.transferred_bytes == 30


def test_upload_with_progress_streams_verbose_and_emits_phases():
    runner = FakeRunner(lines=UPLOAD_LINES)
    phases = []
    result = ProtonDisk(runner=runner).upload(
        "./a", "/my-files", conflict="replace", progress=phases.append)
    assert runner.streaming_calls[0] == (
        "filesystem", "upload", "--verbose", "--conflict-strategy", "replace", "./a", "/my-files")
    assert phases == ["Starting…", "Encrypting…", "Uploading…"]  # metric line produced no phase
    assert result.transferred_bytes == 30


def test_download_with_progress_streams_verbose():
    lines = [
        "2026 INFO [download] revision X: Starting download",
        "2026 DEBUG [download] revision X: block 1: Downloading",
        "2026 DEBUG [download] revision X: block 1: Decrypting",
        '{"transferredItems":1,"transferredBytes":30,"skippedItems":0,"failedItems":0,"failures":[]}',
    ]
    runner = FakeRunner(lines=lines)
    phases = []
    ProtonDisk(runner=runner).download("/my-files/a", "./out", progress=phases.append)
    assert runner.streaming_calls[0] == (
        "filesystem", "download", "--verbose", "/my-files/a", "./out")
    assert phases == ["Starting…", "Downloading…", "Decrypting…"]


def test_download_without_progress_uses_plain_run():
    runner = FakeRunner()
    ProtonDisk(runner=runner).download("/my-files/a", "./out")
    assert runner.calls[0] == ("filesystem", "download", "/my-files/a", "./out")
    assert runner.streaming_calls == []

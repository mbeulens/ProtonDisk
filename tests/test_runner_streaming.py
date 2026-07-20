"""Tests for CLIRunner.run_streaming (line-by-line output + final JSON extraction)."""
import subprocess

import pytest

from protondisk.core.runner import CLIRunner
from protondisk.core.errors import AuthError


class _FakePopen:
    def __init__(self, lines, returncode=0):
        # lines as they'd come from an iterated text pipe (with trailing newline)
        self.stdout = iter(line if line.endswith("\n") else line + "\n" for line in lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode


def _runner(monkeypatch, lines, returncode=0):
    monkeypatch.setattr("protondisk.core.runner.shutil.which",
                        lambda _: "/usr/local/bin/proton-drive")
    monkeypatch.setattr(
        subprocess, "Popen",
        lambda *a, **k: _FakePopen(lines, returncode),
    )
    return CLIRunner()


VERBOSE_UPLOAD = [
    "\x1b[1;90m2026 DEBUG [cli] Loading session\x1b[0m",
    "2026 INFO [upload] revision X: Starting upload",
    "2026 DEBUG [upload] revision X: Encrypting block 1",
    '2026 INFO [metric] performance {"type":"content_encryption","bytesProcessed":30}',
    "2026 INFO [upload] revision X: Uploading",
    '{"transferredItems":1,"transferredBytes":30,"skippedItems":0,"failedItems":0,"failures":[]}',
    "2026 DEBUG [cli] Disposing events manager",
]


def test_streaming_calls_on_line_for_each_line(monkeypatch):
    runner = _runner(monkeypatch, VERBOSE_UPLOAD)
    seen = []
    result = runner.run_streaming("filesystem", "upload", "--verbose", "a", "/my-files",
                                  on_line=seen.append)
    assert len(seen) == len(VERBOSE_UPLOAD)          # every line streamed
    assert "Encrypting block 1" in seen[2]


def test_streaming_returns_last_json_result_ignoring_noise(monkeypatch):
    runner = _runner(monkeypatch, VERBOSE_UPLOAD)
    result = runner.run_streaming("filesystem", "upload", "--verbose", "a", "/my-files")
    # the metric line contains JSON too, but not at line start; the result line wins
    assert result == {"transferredItems": 1, "transferredBytes": 30,
                      "skippedItems": 0, "failedItems": 0, "failures": []}


def test_streaming_empty_output_returns_empty_dict(monkeypatch):
    runner = _runner(monkeypatch, ["2026 DEBUG [cli] nothing useful"])
    assert runner.run_streaming("filesystem", "upload", "--verbose", "a", "/x") == {}


def test_streaming_nonzero_exit_maps_error(monkeypatch):
    runner = _runner(monkeypatch, ["You need to login first"], returncode=1)
    with pytest.raises(AuthError):
        runner.run_streaming("filesystem", "upload", "--verbose", "a", "/x")

import json
import subprocess

import pytest

from protondisk.core.runner import CLIRunner, map_error
from protondisk.core.errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
)


class _Completed:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _which(_):
    return "/usr/local/bin/proton-drive"


def test_discovery_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", lambda _: None)
    with pytest.raises(CLINotFoundError):
        CLIRunner()


def test_run_parses_json_array(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Completed(0, stdout=json.dumps([{"path": "/my-files"}]))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CLIRunner().run("filesystem", "list", "/")
    assert result == [{"path": "/my-files"}]
    assert captured["cmd"] == [
        "/usr/local/bin/proton-drive", "filesystem", "list", "/", "--json"]


def test_run_undefined_stdout_returns_empty_dict(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **k: _Completed(0, stdout="undefined\n"))
    assert CLIRunner().run("sharing", "status", "/my-files/x") == {}


def test_run_empty_stdout_returns_empty_dict(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: _Completed(0, stdout=""))
    assert CLIRunner().run("auth", "logout") == {}


def test_run_nonzero_maps_stderr_login_message(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **k: _Completed(1, stdout="", stderr="You need to login first"))
    with pytest.raises(AuthError):
        CLIRunner().run("filesystem", "list", "/my-files")


@pytest.mark.parametrize("text,exc", [
    ("Path not found", NotFoundError),
    ("You need to login first", AuthError),
    ("File already exists", ConflictError),
    ("Rate limit exceeded", RateLimitError),
    ("Too many requests, slow down", RateLimitError),
    ("Something weird happened", ProtonDiskError),
])
def test_map_error_classification(text, exc):
    err = map_error(1, "", text)
    assert isinstance(err, exc) and str(err)


def test_map_error_prefers_json_error_message():
    stdout = json.dumps({"error": {"message": "Rate limit hit, slow down"}})
    err = map_error(1, stdout, "")
    assert isinstance(err, RateLimitError) and "Rate limit" in str(err)


def test_run_timeout_maps_to_protondisk_error(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ProtonDiskError):
        CLIRunner().run("filesystem", "list", "/my-files", timeout=1)


def test_run_passes_timeout_to_subprocess(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", _which)
    seen = {}
    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return _Completed(0, stdout="{}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    CLIRunner().run("filesystem", "list", "/my-files")        # default
    assert seen["timeout"] == 120
    CLIRunner().run("filesystem", "download", "a", "b", timeout=None)  # transfer opt-out
    assert seen["timeout"] is None

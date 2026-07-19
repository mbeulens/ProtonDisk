# ProtonDisk Milestone 1 — Core CLI Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `protondisk.core` — a typed Python wrapper around the official `proton-drive` CLI that both the future GUI and FUSE mount will consume.

**Architecture:** A thin subprocess layer (`CLIRunner`) is the only code that touches the `proton-drive` binary. It runs commands with `--json`, parses stdout, and maps failures to a single exception hierarchy. A `ProtonDisk` façade exposes typed methods (auth, browse, transfer, organize, share) returning dataclasses. Everything above the runner is pure Python and unit-tested by faking the subprocess/runner boundary — no Proton account needed.

**Tech Stack:** Python 3.12+, standard library only for the core (`subprocess`, `json`, `shutil`, `dataclasses`, `argparse`), `pytest` for tests.

## Global Constraints

- **Python:** 3.12+ (`requires-python = ">=3.12"`). Linux only.
- **Core has zero third-party dependencies** — stdlib only. (GUI/mount deps come in later milestones.)
- **Single dependency point:** only `protondisk/core/runner.py` may invoke the `proton-drive` binary. No other module shells out.
- **TDD:** every task writes a failing test first, then the minimal code to pass.
- **Versioning (project GIT rules):** the `VERSION` file is the single source of truth. **Every commit bumps the patch** and is **pushed to `dev`**. This plan's commits run 0.1.3 → 0.1.12 (the plan document itself was committed at 0.1.2). Skip any version with a `13` segment using commit message `"To be sure to be sure!"` (none occur in this plan). When the milestone completes, a separate **"Bump minor"** step takes it to **0.2.0** (CHANGELOG + README, merge `dev`→`main`).
- **Assumed CLI shapes:** the exact `proton-drive --json` output schemas and some subcommand spellings (`filesystem mkdir`, `filesystem move`) are **assumed** from the launch article's examples, since the binary is not yet installed here. They are isolated in `models.py` (parsing) and `client.py` (argv), so reconciling with the real binary is a localized change. Argv that IS confirmed by the article: `auth login`, `filesystem list`, `filesystem upload … --conflict-strategy`, `filesystem download`, `sharing status`, `sharing invite --user --role --message`.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'` and end messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File Structure

```
protondisk/
├── __init__.py
├── core/
│   ├── __init__.py       # public exports: ProtonDisk, models, errors
│   ├── errors.py         # exception hierarchy
│   ├── models.py         # Entry, AuthStatus, TransferResult, ShareInfo + from_json
│   ├── runner.py         # CLIRunner: binary discovery, _run, error mapping
│   └── client.py         # ProtonDisk façade
└── cli.py                # thin `protondisk` entrypoint (version, auth-status, ls)
tests/
├── test_errors.py
├── test_models.py
├── test_runner.py
├── test_client_auth.py
├── test_client_browse.py
├── test_client_transfer.py
├── test_client_organize.py
├── test_client_sharing.py
└── test_cli.py
pyproject.toml
```

---

### Task 1: Project scaffolding, packaging, and test harness

**Files:**
- Create: `pyproject.toml`
- Create: `protondisk/__init__.py`
- Create: `protondisk/core/__init__.py`
- Test: `tests/test_import.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `protondisk` package; `VERSION` file drives `protondisk.__version__` and packaging version.

- [ ] **Step 1: Write the failing test**

`tests/test_import.py`:
```python
import protondisk


def test_package_exposes_version():
    assert isinstance(protondisk.__version__, str)
    assert protondisk.__version__ != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk'`

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[project]
name = "protondisk"
description = "Use Proton Drive as a mounted disk and graphical browser on Linux"
readme = "README.md"
requires-python = ">=3.12"
dynamic = ["version"]
dependencies = []

[project.optional-dependencies]
gui = ["PyGObject"]
mount = ["pyfuse3"]
dev = ["pytest"]

[project.scripts]
protondisk = "protondisk.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.dynamic]
version = { file = "VERSION" }

[tool.setuptools.packages.find]
include = ["protondisk*"]
```

`protondisk/__init__.py`:
```python
"""ProtonDisk — Proton Drive as a mounted disk and graphical browser."""
from pathlib import Path

_version_file = Path(__file__).resolve().parent.parent / "VERSION"
try:
    __version__ = _version_file.read_text(encoding="utf-8").strip()
except OSError:  # pragma: no cover - fallback when packaged without VERSION
    __version__ = "0.0.0"

__all__ = ["__version__"]
```

`protondisk/core/__init__.py`:
```python
"""ProtonDisk core: typed wrapper around the official proton-drive CLI."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.3\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add pyproject.toml protondisk/__init__.py protondisk/core/__init__.py tests/test_import.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): package scaffolding and test harness (v0.1.3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 2: Exception hierarchy

**Files:**
- Create: `protondisk/core/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ProtonDiskError` (base) and subclasses `CLINotFoundError`, `AuthError`, `NotFoundError`, `ConflictError`, `RateLimitError`. All accept a message string.

- [ ] **Step 1: Write the failing test**

`tests/test_errors.py`:
```python
import pytest

from protondisk.core.errors import (
    ProtonDiskError,
    CLINotFoundError,
    AuthError,
    NotFoundError,
    ConflictError,
    RateLimitError,
)


@pytest.mark.parametrize(
    "subclass",
    [CLINotFoundError, AuthError, NotFoundError, ConflictError, RateLimitError],
)
def test_all_errors_derive_from_base(subclass):
    err = subclass("boom")
    assert isinstance(err, ProtonDiskError)
    assert str(err) == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.core.errors'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/core/errors.py`:
```python
"""Exception hierarchy for ProtonDisk core."""


class ProtonDiskError(Exception):
    """Base class for all ProtonDisk errors."""


class CLINotFoundError(ProtonDiskError):
    """The proton-drive binary could not be located."""


class AuthError(ProtonDiskError):
    """Not logged in, or the session has expired."""


class NotFoundError(ProtonDiskError):
    """A requested path does not exist."""


class ConflictError(ProtonDiskError):
    """A name collision or upload conflict occurred."""


class RateLimitError(ProtonDiskError):
    """Proton fair-use throttling was triggered."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.4\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/errors.py tests/test_errors.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): exception hierarchy (v0.1.4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 3: Data models and JSON parsing

**Files:**
- Create: `protondisk/core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (frozen dataclasses, each with a `from_json(data: dict)` classmethod):
  - `Entry(name: str, path: str, is_dir: bool, size: int | None, mtime: float | None, id: str | None)`; `Entry.from_json(data, *, parent="")`. Reads `name`; `is_dir = data.get("type") == "folder"`; `size = data.get("size")`; `mtime = data.get("modifiedAt")`; `path = data.get("path") or f"{parent.rstrip('/')}/{name}"`; `id = data.get("id")`.
  - `AuthStatus(logged_in: bool, account: str | None)`; `from_json` reads `loggedIn` and `account`.
  - `TransferResult(source: str, destination: str, bytes: int | None)`; `from_json` reads `source`, `destination`, `bytes`.
  - `ShareInfo(path: str, shared: bool, members: list[str])`; `from_json` reads `path`, `shared`, `members` (list of dicts each with `email`).

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from protondisk.core.models import Entry, AuthStatus, TransferResult, ShareInfo


def test_entry_folder_from_json_derives_path_from_parent():
    e = Entry.from_json({"name": "Reports", "type": "folder"}, parent="/my-files")
    assert e.name == "Reports"
    assert e.is_dir is True
    assert e.path == "/my-files/Reports"
    assert e.size is None


def test_entry_file_uses_explicit_path_and_fields():
    e = Entry.from_json(
        {"name": "q3.pdf", "type": "file", "size": 1024,
         "modifiedAt": 1720000000.0, "path": "/my-files/q3.pdf", "id": "abc"},
        parent="/my-files",
    )
    assert e.is_dir is False
    assert e.size == 1024
    assert e.mtime == 1720000000.0
    assert e.path == "/my-files/q3.pdf"
    assert e.id == "abc"


def test_auth_status_logged_in():
    a = AuthStatus.from_json({"loggedIn": True, "account": "user@pm.me"})
    assert a.logged_in is True
    assert a.account == "user@pm.me"


def test_auth_status_logged_out_defaults():
    a = AuthStatus.from_json({"loggedIn": False})
    assert a.logged_in is False
    assert a.account is None


def test_transfer_result_from_json():
    t = TransferResult.from_json(
        {"source": "./a.txt", "destination": "/my-files/a.txt", "bytes": 12})
    assert t.source == "./a.txt"
    assert t.destination == "/my-files/a.txt"
    assert t.bytes == 12


def test_share_info_extracts_member_emails():
    s = ShareInfo.from_json(
        {"path": "/my-files/Reports", "shared": True,
         "members": [{"email": "a@pm.me"}, {"email": "b@pm.me"}]})
    assert s.shared is True
    assert s.members == ["a@pm.me", "b@pm.me"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.core.models'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/core/models.py`:
```python
"""Typed dataclasses parsed from `proton-drive --json` output.

The exact JSON field names are assumed from the launch article and MUST be
reconciled against the real binary. Keep all field-name knowledge in this file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    is_dir: bool
    size: int | None
    mtime: float | None
    id: str | None

    @classmethod
    def from_json(cls, data: dict, *, parent: str = "") -> "Entry":
        name = data["name"]
        path = data.get("path") or f"{parent.rstrip('/')}/{name}"
        return cls(
            name=name,
            path=path,
            is_dir=data.get("type") == "folder",
            size=data.get("size"),
            mtime=data.get("modifiedAt"),
            id=data.get("id"),
        )


@dataclass(frozen=True)
class AuthStatus:
    logged_in: bool
    account: str | None

    @classmethod
    def from_json(cls, data: dict) -> "AuthStatus":
        return cls(logged_in=bool(data.get("loggedIn")), account=data.get("account"))


@dataclass(frozen=True)
class TransferResult:
    source: str
    destination: str
    bytes: int | None

    @classmethod
    def from_json(cls, data: dict) -> "TransferResult":
        return cls(
            source=data.get("source", ""),
            destination=data.get("destination", ""),
            bytes=data.get("bytes"),
        )


@dataclass(frozen=True)
class ShareInfo:
    path: str
    shared: bool
    members: list[str]

    @classmethod
    def from_json(cls, data: dict) -> "ShareInfo":
        members = [m.get("email", "") for m in data.get("members", [])]
        return cls(
            path=data.get("path", ""),
            shared=bool(data.get("shared")),
            members=members,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.5\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/models.py tests/test_models.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): typed data models with JSON parsing (v0.1.5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 4: CLIRunner — binary discovery, execution, error mapping

**Files:**
- Create: `protondisk/core/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: exceptions from `errors.py`.
- Produces:
  - `CLIRunner(binary: str | None = None)`. If `binary` is None, discover via `shutil.which("proton-drive")`; if not found, raise `CLINotFoundError`.
  - `CLIRunner.run(*args: str, input_text: str | None = None) -> dict | list`. Invokes `[binary, *args, "--json"]` via `subprocess.run(..., capture_output=True, text=True)`. On return code 0, parses stdout as JSON and returns it (or `{}` for empty stdout). On non-zero, calls `map_error(returncode, stdout, stderr)` and raises.
  - `map_error(returncode: int, stdout: str, stderr: str) -> ProtonDiskError` — module-level function. Extracts a message (prefer a JSON `{"error": {"message": ...}}` in stdout, else stderr, else stdout), lowercases it for matching, and classifies: contains `not found`/`no such`→`NotFoundError`; `unauthorized`/`not logged in`/`login`/`auth`→`AuthError`; `conflict`/`already exists`→`ConflictError`; `rate`/`throttl`/`429`→`RateLimitError`; otherwise `ProtonDiskError`. Returned exception carries the extracted message.

- [ ] **Step 1: Write the failing test**

`tests/test_runner.py`:
```python
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


def test_discovery_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", lambda _: None)
    with pytest.raises(CLINotFoundError):
        CLIRunner()


def test_run_parses_json_stdout(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", lambda _: "/usr/bin/proton-drive")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Completed(0, stdout=json.dumps({"loggedIn": True}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = CLIRunner()
    result = runner.run("auth", "status")
    assert result == {"loggedIn": True}
    assert captured["cmd"] == ["/usr/bin/proton-drive", "auth", "status", "--json"]


def test_run_empty_stdout_returns_empty_dict(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", lambda _: "/usr/bin/proton-drive")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: _Completed(0, stdout=""))
    assert CLIRunner().run("auth", "logout") == {}


def test_run_maps_nonzero_to_exception(monkeypatch):
    monkeypatch.setattr("protondisk.core.runner.shutil.which", lambda _: "/usr/bin/proton-drive")
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **k: _Completed(1, stdout="", stderr="Path not found: /nope"),
    )
    with pytest.raises(NotFoundError):
        CLIRunner().run("filesystem", "list", "/nope")


@pytest.mark.parametrize("text,exc", [
    ("Path not found", NotFoundError),
    ("You are not logged in", AuthError),
    ("File already exists", ConflictError),
    ("Rate limit exceeded", RateLimitError),
    ("Something weird happened", ProtonDiskError),
])
def test_map_error_classification(text, exc):
    err = map_error(1, "", text)
    assert isinstance(err, exc)
    assert str(err)


def test_map_error_prefers_json_error_message():
    stdout = json.dumps({"error": {"message": "Rate limit hit, slow down"}})
    err = map_error(1, stdout, "")
    assert isinstance(err, RateLimitError)
    assert "Rate limit" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.core.runner'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/core/runner.py`:
```python
"""The only module that invokes the proton-drive binary."""
from __future__ import annotations

import json
import shutil
import subprocess

from .errors import (
    ProtonDiskError,
    CLINotFoundError,
    AuthError,
    NotFoundError,
    ConflictError,
    RateLimitError,
)

BINARY_NAME = "proton-drive"


def _extract_message(stdout: str, stderr: str) -> str:
    try:
        payload = json.loads(stdout)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            msg = payload["error"].get("message")
            if msg:
                return str(msg)
    except (ValueError, TypeError):
        pass
    return (stderr or stdout or "proton-drive failed").strip()


def map_error(returncode: int, stdout: str, stderr: str) -> ProtonDiskError:
    message = _extract_message(stdout, stderr)
    lowered = message.lower()
    if "not found" in lowered or "no such" in lowered:
        return NotFoundError(message)
    if any(k in lowered for k in ("unauthorized", "not logged in", "login", "auth")):
        return AuthError(message)
    if "conflict" in lowered or "already exists" in lowered:
        return ConflictError(message)
    if "rate" in lowered or "throttl" in lowered or "429" in lowered:
        return RateLimitError(message)
    return ProtonDiskError(message)


class CLIRunner:
    def __init__(self, binary: str | None = None) -> None:
        resolved = binary or shutil.which(BINARY_NAME)
        if not resolved:
            raise CLINotFoundError(
                f"Could not find the '{BINARY_NAME}' binary on PATH. "
                "Install the Proton Drive CLI or set its path in config."
            )
        self.binary = resolved

    def run(self, *args: str, input_text: str | None = None) -> dict | list:
        cmd = [self.binary, *args, "--json"]
        completed = subprocess.run(
            cmd, capture_output=True, text=True, input=input_text
        )
        if completed.returncode != 0:
            raise map_error(completed.returncode, completed.stdout, completed.stderr)
        stdout = completed.stdout.strip()
        if not stdout:
            return {}
        return json.loads(stdout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.6\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/runner.py tests/test_runner.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): CLIRunner with discovery and error mapping (v0.1.6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 5: ProtonDisk façade — auth

**Files:**
- Create: `protondisk/core/client.py`
- Test: `tests/test_client_auth.py`

**Interfaces:**
- Consumes: `CLIRunner` (Task 4), `AuthStatus` (Task 3).
- Produces:
  - `ProtonDisk(runner=None)` — stores an injected runner; if `None`, constructs `CLIRunner()` lazily is NOT required here (accept the injected one; default `CLIRunner()`).
  - `auth_status() -> AuthStatus` → `runner.run("auth", "status")`.
  - `login() -> None` → `runner.run("auth", "login")`.
  - `logout() -> None` → `runner.run("auth", "logout")`.
- Test double: a `FakeRunner` recording `.calls` (list of arg tuples) and returning queued dicts.

- [ ] **Step 1: Write the failing test**

`tests/test_client_auth.py`:
```python
from protondisk.core.client import ProtonDisk
from protondisk.core.models import AuthStatus


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_auth_status_returns_parsed_status():
    runner = FakeRunner([{"loggedIn": True, "account": "user@pm.me"}])
    disk = ProtonDisk(runner=runner)
    status = disk.auth_status()
    assert status == AuthStatus(logged_in=True, account="user@pm.me")
    assert runner.calls[0] == ("auth", "status")


def test_login_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).login()
    assert runner.calls[0] == ("auth", "login")


def test_logout_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).logout()
    assert runner.calls[0] == ("auth", "logout")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.core.client'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/core/client.py`:
```python
"""ProtonDisk façade: typed methods over the CLIRunner."""
from __future__ import annotations

from .runner import CLIRunner
from .models import AuthStatus, Entry, TransferResult, ShareInfo


class ProtonDisk:
    def __init__(self, runner: CLIRunner | None = None) -> None:
        self._runner = runner or CLIRunner()

    # --- auth ---
    def auth_status(self) -> AuthStatus:
        return AuthStatus.from_json(self._runner.run("auth", "status"))

    def login(self) -> None:
        self._runner.run("auth", "login")

    def logout(self) -> None:
        self._runner.run("auth", "logout")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.7\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_auth.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): ProtonDisk auth methods (v0.1.7)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 6: ProtonDisk façade — browsing (list, stat)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_browse.py`

**Interfaces:**
- Consumes: `FakeRunner` pattern (Task 5), `Entry` (Task 3).
- Produces (added to `ProtonDisk`):
  - `list(path: str) -> list[Entry]` → `runner.run("filesystem", "list", path)`; reads the `items` key (default `[]`); each item parsed with `Entry.from_json(item, parent=path)`.
  - `stat(path: str) -> Entry` → lists the parent directory and returns the entry whose `name` matches the basename; raises `NotFoundError` if absent. Root path `/my-files` (or `/`) returns a synthetic directory `Entry(name=basename, path=path, is_dir=True, size=None, mtime=None, id=None)`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_browse.py`:
```python
import pytest

from protondisk.core.client import ProtonDisk
from protondisk.core.errors import NotFoundError


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_list_parses_items_with_parent_path():
    runner = FakeRunner([{"items": [
        {"name": "Reports", "type": "folder"},
        {"name": "q3.pdf", "type": "file", "size": 10},
    ]}])
    entries = ProtonDisk(runner=runner).list("/my-files")
    assert runner.calls[0] == ("filesystem", "list", "/my-files")
    assert [e.name for e in entries] == ["Reports", "q3.pdf"]
    assert entries[0].path == "/my-files/Reports"
    assert entries[0].is_dir is True
    assert entries[1].size == 10


def test_list_missing_items_key_returns_empty():
    assert ProtonDisk(runner=FakeRunner([{}])).list("/my-files") == []


def test_stat_finds_entry_in_parent_listing():
    runner = FakeRunner([{"items": [
        {"name": "q3.pdf", "type": "file", "size": 10},
    ]}])
    entry = ProtonDisk(runner=runner).stat("/my-files/q3.pdf")
    assert entry.name == "q3.pdf"
    assert entry.is_dir is False
    assert runner.calls[0] == ("filesystem", "list", "/my-files")


def test_stat_missing_entry_raises_not_found():
    runner = FakeRunner([{"items": []}])
    with pytest.raises(NotFoundError):
        ProtonDisk(runner=runner).stat("/my-files/missing.pdf")


def test_stat_root_is_synthetic_directory():
    runner = FakeRunner()
    entry = ProtonDisk(runner=runner).stat("/my-files")
    assert entry.is_dir is True
    assert entry.path == "/my-files"
    assert runner.calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_browse.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'list'`

- [ ] **Step 3: Write minimal implementation**

Add to `protondisk/core/client.py` (import `NotFoundError`, add a helper, and the methods). Update the imports line and append methods:

```python
from .errors import NotFoundError
```

Append inside the `ProtonDisk` class:
```python
    # --- browsing ---
    _ROOTS = ("/", "/my-files")

    def list(self, path: str) -> list[Entry]:
        data = self._runner.run("filesystem", "list", path)
        items = data.get("items", []) if isinstance(data, dict) else []
        return [Entry.from_json(item, parent=path) for item in items]

    def stat(self, path: str) -> Entry:
        normalized = path.rstrip("/") or "/"
        if normalized in self._ROOTS:
            name = normalized.rstrip("/").rsplit("/", 1)[-1] or "/"
            return Entry(name=name, path=normalized, is_dir=True,
                         size=None, mtime=None, id=None)
        parent, _, base = normalized.rpartition("/")
        parent = parent or "/"
        for entry in self.list(parent):
            if entry.name == base:
                return entry
        raise NotFoundError(f"No such path: {path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_browse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.8\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_browse.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): browsing methods list and stat (v0.1.8)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 7: ProtonDisk façade — transfer (upload, download)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_transfer.py`

**Interfaces:**
- Consumes: `TransferResult` (Task 3).
- Produces (added to `ProtonDisk`):
  - `upload(local: str, remote: str, *, conflict: str = "skip") -> TransferResult` → `runner.run("filesystem", "upload", local, remote, "--conflict-strategy", conflict)`.
  - `download(remote: str, local: str) -> TransferResult` → `runner.run("filesystem", "download", remote, local)`.
  - Both parse the runner result with `TransferResult.from_json`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_transfer.py`:
```python
from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_upload_passes_conflict_strategy_and_parses_result():
    runner = FakeRunner([
        {"source": "./a.txt", "destination": "/my-files/a.txt", "bytes": 5}])
    result = ProtonDisk(runner=runner).upload("./a.txt", "/my-files", conflict="skip")
    assert runner.calls[0] == (
        "filesystem", "upload", "./a.txt", "/my-files", "--conflict-strategy", "skip")
    assert result.bytes == 5
    assert result.destination == "/my-files/a.txt"


def test_upload_default_conflict_is_skip():
    runner = FakeRunner()
    ProtonDisk(runner=runner).upload("./a.txt", "/my-files")
    assert runner.calls[0][-2:] == ("--conflict-strategy", "skip")


def test_download_parses_result():
    runner = FakeRunner([
        {"source": "/my-files/a.txt", "destination": "./a.txt", "bytes": 5}])
    result = ProtonDisk(runner=runner).download("/my-files/a.txt", "./")
    assert runner.calls[0] == ("filesystem", "download", "/my-files/a.txt", "./")
    assert result.source == "/my-files/a.txt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_transfer.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'upload'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- transfer ---
    def upload(self, local: str, remote: str, *, conflict: str = "skip") -> TransferResult:
        data = self._runner.run(
            "filesystem", "upload", local, remote, "--conflict-strategy", conflict)
        return TransferResult.from_json(data)

    def download(self, remote: str, local: str) -> TransferResult:
        data = self._runner.run("filesystem", "download", remote, local)
        return TransferResult.from_json(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_transfer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.9\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_transfer.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): transfer methods upload and download (v0.1.9)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 8: ProtonDisk façade — organize (mkdir, move, trash)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_organize.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (added to `ProtonDisk`; argv spellings are **assumed** and flagged in Global Constraints):
  - `mkdir(path: str) -> None` → `runner.run("filesystem", "mkdir", path)`.
  - `move(src: str, dst: str) -> None` → `runner.run("filesystem", "move", src, dst)`.
  - `trash(path: str) -> None` → `runner.run("filesystem", "trash", path)`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_organize.py`:
```python
from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, *args, input_text=None):
        self.calls.append(args)
        return {}


def test_mkdir_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).mkdir("/my-files/New")
    assert runner.calls[0] == ("filesystem", "mkdir", "/my-files/New")


def test_move_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).move("/my-files/a.txt", "/my-files/b.txt")
    assert runner.calls[0] == ("filesystem", "move", "/my-files/a.txt", "/my-files/b.txt")


def test_trash_invokes_cli():
    runner = FakeRunner()
    ProtonDisk(runner=runner).trash("/my-files/old.txt")
    assert runner.calls[0] == ("filesystem", "trash", "/my-files/old.txt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_organize.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'mkdir'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- organize ---
    def mkdir(self, path: str) -> None:
        self._runner.run("filesystem", "mkdir", path)

    def move(self, src: str, dst: str) -> None:
        self._runner.run("filesystem", "move", src, dst)

    def trash(self, path: str) -> None:
        self._runner.run("filesystem", "trash", path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_organize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.10\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_organize.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): organize methods mkdir move trash (v0.1.10)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 9: ProtonDisk façade — sharing + public exports

**Files:**
- Modify: `protondisk/core/client.py`
- Modify: `protondisk/core/__init__.py`
- Test: `tests/test_client_sharing.py`

**Interfaces:**
- Consumes: `ShareInfo` (Task 3).
- Produces (added to `ProtonDisk`):
  - `sharing_status(path: str) -> ShareInfo` → `runner.run("sharing", "status", path)`.
  - `sharing_invite(path: str, user: str, role: str = "editor", message: str = "") -> None` → `runner.run("sharing", "invite", "--user", user, "--role", role, "--message", message, path)`.
- Also: `protondisk/core/__init__.py` re-exports `ProtonDisk`, all models, and all errors so consumers can `from protondisk.core import ProtonDisk, Entry, AuthError`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_sharing.py`:
```python
from protondisk.core import ProtonDisk, ShareInfo, AuthError  # exercises re-exports


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
        self.calls.append(args)
        return self._results.pop(0) if self._results else {}


def test_sharing_status_parses_members():
    runner = FakeRunner([{"path": "/my-files/Reports", "shared": True,
                          "members": [{"email": "a@pm.me"}]}])
    info = ProtonDisk(runner=runner).sharing_status("/my-files/Reports")
    assert isinstance(info, ShareInfo)
    assert info.members == ["a@pm.me"]
    assert runner.calls[0] == ("sharing", "status", "/my-files/Reports")


def test_sharing_invite_passes_all_flags():
    runner = FakeRunner()
    ProtonDisk(runner=runner).sharing_invite(
        "/my-files/Reports", "b@pm.me", role="editor", message="pls review")
    assert runner.calls[0] == (
        "sharing", "invite", "--user", "b@pm.me", "--role", "editor",
        "--message", "pls review", "/my-files/Reports")


def test_error_is_reexported():
    assert issubclass(AuthError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_sharing.py -v`
Expected: FAIL — `ImportError: cannot import name 'ProtonDisk' from 'protondisk.core'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- sharing ---
    def sharing_status(self, path: str) -> ShareInfo:
        return ShareInfo.from_json(self._runner.run("sharing", "status", path))

    def sharing_invite(self, path: str, user: str, role: str = "editor",
                       message: str = "") -> None:
        self._runner.run(
            "sharing", "invite", "--user", user, "--role", role,
            "--message", message, path)
```

Replace `protondisk/core/__init__.py` with:
```python
"""ProtonDisk core: typed wrapper around the official proton-drive CLI."""
from .client import ProtonDisk
from .models import Entry, AuthStatus, TransferResult, ShareInfo
from .errors import (
    ProtonDiskError,
    CLINotFoundError,
    AuthError,
    NotFoundError,
    ConflictError,
    RateLimitError,
)

__all__ = [
    "ProtonDisk",
    "Entry",
    "AuthStatus",
    "TransferResult",
    "ShareInfo",
    "ProtonDiskError",
    "CLINotFoundError",
    "AuthError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_sharing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '0.1.11\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py protondisk/core/__init__.py tests/test_client_sharing.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): sharing methods and public core exports (v0.1.11)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 10: Thin `protondisk` CLI entrypoint

**Files:**
- Create: `protondisk/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ProtonDisk` (Task 5-9), `ProtonDiskError` (Task 2), `__version__` (Task 1).
- Produces:
  - `main(argv: list[str] | None = None, disk: ProtonDisk | None = None) -> int` — argparse with subcommands `version`, `auth-status`, `ls PATH`. `disk` is injectable for testing (defaults to `ProtonDisk()`). Prints human-readable lines. Returns `0` on success; on `ProtonDiskError` prints `error: <msg>` to stderr and returns `1`. `version` prints `__version__` and never constructs a disk.
  - This proves the whole core end-to-end and is the manual live-test tool: `protondisk auth-status`, `protondisk ls /my-files`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import protondisk
from protondisk.cli import main
from protondisk.core.models import AuthStatus, Entry
from protondisk.core.errors import AuthError


class FakeDisk:
    def __init__(self, *, status=None, entries=None, error=None):
        self._status = status
        self._entries = entries or []
        self._error = error

    def auth_status(self):
        if self._error:
            raise self._error
        return self._status

    def list(self, path):
        if self._error:
            raise self._error
        return self._entries


def test_version_prints_version(capsys):
    rc = main(["version"])
    assert rc == 0
    assert protondisk.__version__ in capsys.readouterr().out


def test_auth_status_prints_account(capsys):
    disk = FakeDisk(status=AuthStatus(logged_in=True, account="user@pm.me"))
    rc = main(["auth-status"], disk=disk)
    assert rc == 0
    assert "user@pm.me" in capsys.readouterr().out


def test_ls_lists_entries(capsys):
    disk = FakeDisk(entries=[
        Entry("Reports", "/my-files/Reports", True, None, None, None),
        Entry("q3.pdf", "/my-files/q3.pdf", False, 10, None, None),
    ])
    rc = main(["ls", "/my-files"], disk=disk)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Reports" in out and "q3.pdf" in out


def test_error_returns_1_and_prints_stderr(capsys):
    disk = FakeDisk(error=AuthError("not logged in"))
    rc = main(["auth-status"], disk=disk)
    assert rc == 1
    assert "not logged in" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.cli'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/cli.py`:
```python
"""Thin command-line entrypoint exercising the ProtonDisk core."""
from __future__ import annotations

import argparse
import sys

import protondisk
from .core.client import ProtonDisk
from .core.errors import ProtonDiskError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="protondisk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the ProtonDisk version")
    sub.add_parser("auth-status", help="show login status")
    ls = sub.add_parser("ls", help="list a Drive folder")
    ls.add_argument("path")
    return parser


def main(argv: list[str] | None = None, disk: ProtonDisk | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "version":
        print(protondisk.__version__)
        return 0

    disk = disk or ProtonDisk()
    try:
        if args.command == "auth-status":
            status = disk.auth_status()
            if status.logged_in:
                print(f"logged in as {status.account}")
            else:
                print("not logged in")
        elif args.command == "ls":
            for entry in disk.list(args.path):
                marker = "/" if entry.is_dir else " "
                print(f"{marker} {entry.name}")
    except ProtonDiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ -v`
Expected: PASS (all suites, full core + CLI)

- [ ] **Step 5: Commit**

```bash
printf '0.1.12\n' > VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/cli.py tests/test_cli.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): thin protondisk CLI entrypoint (v0.1.12)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

## Milestone Completion — "Bump minor" to 0.2.0

After all 10 tasks pass, when you (the user) say **"Bump minor"**, I will:

1. Create/update `CHANGELOG.md` documenting the 0.2.0 core release.
2. Update `README.md` (install prerequisites, `protondisk` usage, core API overview).
3. Set `VERSION` to `0.2.0`.
4. Commit to `dev`, then merge `dev` → `main`, and push both branches.

---

## Self-Review

**1. Spec coverage (Milestone 1 scope):**
- Core API (auth/list/stat/upload/download/mkdir/move/trash/sharing) → Tasks 5-9 ✅
- `_run` subprocess helper + JSON parsing → Task 4 ✅
- Typed dataclasses → Task 3 ✅
- Error hierarchy (all 6 classes incl. `RateLimitError`, `CLINotFoundError`) → Task 2, used in Task 4 ✅
- CLI binary discovery → Task 4 ✅
- Fixture/fake-boundary testing, no account needed → every task ✅
- `protondisk/cli.py` entrypoint → Task 10 ✅
- `pyproject.toml`, package layout, VERSION-driven version → Task 1 ✅
- GUI, mount, config file → **intentionally deferred** to later milestones (out of scope here) ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. ✅

**3. Type consistency:** `ProtonDisk`, `CLIRunner`, `map_error`, `Entry/AuthStatus/TransferResult/ShareInfo.from_json`, and the `FakeRunner.run(*args, input_text=None)` signature are consistent across all tasks. Method names (`auth_status`, `sharing_status`, `sharing_invite`) match the design doc. ✅

**Note carried forward:** assumed `--json` schemas and `filesystem mkdir/move` argv must be reconciled against the real `proton-drive` binary during live testing; the isolation in `models.py`/`client.py` keeps that a localized fix.

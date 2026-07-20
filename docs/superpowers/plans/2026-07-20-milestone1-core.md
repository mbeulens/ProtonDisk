# ProtonDisk Milestone 1 — Core CLI Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `protondisk.core` — a typed Python wrapper around the official `proton-drive` CLI (`cli-drive@0.5.0`) that both the future GUI and FUSE mount will consume.

**Architecture:** A thin subprocess layer (`CLIRunner`) is the only code that touches the `proton-drive` binary. It runs commands with `--json`, parses stdout (JSON array/object, or empty/`undefined` → `{}`), and maps non-zero exits to a single exception hierarchy. A `ProtonDisk` façade exposes typed methods returning dataclasses. Everything above the runner is unit-tested by faking the runner boundary with **real captured JSON shapes** — no Proton account needed in CI.

**Tech Stack:** Python 3.12+, standard library only for the core (`subprocess`, `json`, `shutil`, `datetime`, `dataclasses`, `argparse`), `pytest` for tests.

> **All JSON in this plan is real output captured from `proton-drive` 0.5.0 on a logged-in session (2026-07-20)**, with long `uid` values shortened for readability. Field names and structures are exact.

## Global Constraints

- **Python:** 3.12+ (`requires-python = ">=3.12"`). Linux only.
- **Core has zero third-party dependencies** — stdlib only.
- **Single dependency point:** only `protondisk/core/runner.py` may invoke the `proton-drive` binary.
- **TDD:** every task writes a failing test first, then the minimal code to pass.
- **Versioning (project GIT rules):** the `VERSION` file is the single source of truth. Every task commit runs **`scripts/bump-patch.sh`** (created in Task 1), which increments the patch, **skips any patch equal to 13** (jumping 0.1.13 → 0.1.14) and prints a skip notice to stderr. **When the skip notice appears, that commit's message MUST be exactly `To be sure to be sure!`** (see Task 9, which lands on the skip). Every commit is **pushed to `dev`**. Starting from `VERSION=0.1.4` (after this plan is committed), the tasks land on 0.1.5 … 0.1.12, then 0.1.14 (13 skipped) for Task 9, then 0.1.15 for Task 10.
- **Commit author:** `git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl'`; end messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **Confirmed CLI facts** (from live capture):
  - `list` returns a **top-level JSON array**. `list /` → section stubs `{"path":"/my-files"}`; `list <folder>` → node objects.
  - Node: `uid`, `parentUid`, `name` = `{"ok":bool,"value":str}`, `type` (`file`|`folder`), `totalStorageSize` (files), `modificationTime`/`creationTime` = **ISO 8601 strings**, `ownedBy.email`, `isShared`, `activeRevision` (files). **No `path` field.**
  - `filesystem info <path>` → single node object (the `stat`).
  - `filesystem create-folder <parentPath> <name>`; `filesystem rename <path> <newName>`; `filesystem move <src…> <targetParent>`; `filesystem trash <path…>`. `move`/`trash` → `[{"uid":str,"ok":bool}]`.
  - `filesystem upload -c <strategy> <local…> <parent>` and `filesystem download <remote…> <localFolder>` → `{"transferredItems","transferredBytes","skippedItems","failedItems","failures"}`. Strategies: `merge|keep-both|replace|skip`.
  - No `auth status`: probe via `filesystem info /my-files`, read account from `ownedBy.email`.
  - `sharing status <path>` → literal `undefined` (exit 0) when unshared; may error on undecryptable shares.
  - Errors: exit 1 with plain-text message on **stderr** (e.g. `You need to login first`).

---

## File Structure

```
protondisk/
├── __init__.py           # __version__ from VERSION
├── core/
│   ├── __init__.py       # public exports
│   ├── errors.py         # exception hierarchy
│   ├── models.py         # Entry, AuthStatus, TransferResult, ShareInfo + helpers
│   ├── runner.py         # CLIRunner: discovery, run, error mapping
│   └── client.py         # ProtonDisk façade
└── cli.py                # thin `protondisk` entrypoint
scripts/
└── bump-patch.sh         # VERSION patch bump (skips 13)
tests/
├── test_import.py  test_errors.py  test_models.py  test_runner.py
├── test_client_auth.py  test_client_browse.py  test_client_transfer.py
├── test_client_organize.py  test_client_sharing.py  test_cli.py
pyproject.toml
```

---

### Task 1: Scaffolding, packaging, version-bump script, test harness

**Files:**
- Create: `pyproject.toml`, `protondisk/__init__.py`, `protondisk/core/__init__.py`, `scripts/bump-patch.sh`
- Test: `tests/test_import.py`

**Interfaces:**
- Produces: importable `protondisk` with `__version__` from `VERSION`; `scripts/bump-patch.sh` prints the new version and skips patch 13.

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
except OSError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
```

`protondisk/core/__init__.py`:
```python
"""ProtonDisk core: typed wrapper around the official proton-drive CLI."""
```

`scripts/bump-patch.sh`:
```bash
#!/usr/bin/env bash
# Increment the patch in VERSION. Project rule: skip any patch equal to 13
# (a commit that lands on 13 jumps to 14 and MUST use the message
# "To be sure to be sure!"). Prints the new version to stdout.
set -euo pipefail
IFS=. read -r MAJOR MINOR PATCH < VERSION
PATCH=$((PATCH + 1))
if [ "$PATCH" -eq 13 ]; then
    PATCH=14
    echo "NOTE: skipped patch 13 per project rule -> use commit message 'To be sure to be sure!'" >&2
fi
printf '%s.%s.%s\n' "$MAJOR" "$MINOR" "$PATCH" > VERSION
cat VERSION
```

Make it executable: `chmod +x scripts/bump-patch.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/bump-patch.sh
ver=$(scripts/bump-patch.sh)   # 0.1.4 -> 0.1.5
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add pyproject.toml protondisk/__init__.py protondisk/core/__init__.py \
      scripts/bump-patch.sh tests/test_import.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): scaffolding, packaging, version-bump script (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 2: Exception hierarchy

**Files:**
- Create: `protondisk/core/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Produces: `ProtonDiskError` (base) + `CLINotFoundError`, `AuthError`, `NotFoundError`, `ConflictError`, `RateLimitError`. All accept a message string.

- [ ] **Step 1: Write the failing test**

`tests/test_errors.py`:
```python
import pytest

from protondisk.core.errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
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
ver=$(scripts/bump-patch.sh)   # -> 0.1.6
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/errors.py tests/test_errors.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): exception hierarchy (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 3: Data models and JSON parsing (real shapes)

**Files:**
- Create: `protondisk/core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces module-level helpers and four frozen dataclasses:
  - `_unwrap(result) -> str | None` — returns `result["value"]` when `result` is a dict with `ok` truthy, else `None`.
  - `_parse_iso(s) -> float | None` — parses an ISO 8601 string (with trailing `Z`) to epoch seconds; `None` if falsy.
  - `_basename(path) -> str` — last path segment; `/` for root.
  - `Entry(name: str, path: str, is_dir: bool, size: int | None, mtime: float | None, uid: str | None)` with `from_json(data, *, path=None, parent="")`. Section stub `{"path": "/x"}` (no `type`) → a directory Entry. Otherwise: name from `_unwrap(data["name"])` (fallback `uid`); if `path` given it overrides both path and name (name=`_basename(path)`); else path = `f"{parent.rstrip('/')}/{name}"`; `is_dir = data.get("type") == "folder"`; `size = data.get("totalStorageSize")`; `mtime = _parse_iso(data.get("modificationTime"))`; `uid = data.get("uid")`.
  - `AuthStatus(logged_in: bool, account: str | None)`.
  - `TransferResult(transferred_items: int, transferred_bytes: int, skipped_items: int, failed_items: int, failures: list)` with `from_json`.
  - `ShareInfo(path: str, shared: bool, members: list[str])` with `from_json(data, *, path="")`; empty/`{}` (unshared) → `shared=False, members=[]`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from protondisk.core.models import (
    Entry, AuthStatus, TransferResult, ShareInfo, _unwrap, _parse_iso, _basename,
)

# Real captured node (uid shortened):
FILE_NODE = {
    "uid": "ROOT~FILE",
    "parentUid": "ROOT~PARENT",
    "name": {"ok": True, "value": "kaas.txt"},
    "type": "file",
    "mediaType": "text/plain; charset=utf-8",
    "isShared": False,
    "creationTime": "2026-03-26T00:51:13.000Z",
    "modificationTime": "2026-03-26T00:51:13.000Z",
    "totalStorageSize": 95,
    "ownedBy": {"email": "m.beulens@syntec-one.nl"},
}
FOLDER_NODE = {
    "uid": "ROOT~DIR", "name": {"ok": True, "value": "Test map"},
    "type": "folder", "isShared": False,
    "modificationTime": "2026-03-26T02:17:11.000Z", "folder": {"isImported": False},
}


def test_unwrap_result_object():
    assert _unwrap({"ok": True, "value": "kaas.txt"}) == "kaas.txt"
    assert _unwrap({"ok": False}) is None
    assert _unwrap(None) is None


def test_parse_iso_to_epoch():
    assert _parse_iso("2026-03-26T00:51:13.000Z") == \
        __import__("datetime").datetime(2026, 3, 26, 0, 51, 13,
            tzinfo=__import__("datetime").timezone.utc).timestamp()
    assert _parse_iso(None) is None


def test_basename():
    assert _basename("/my-files/Reports") == "Reports"
    assert _basename("/") == "/"


def test_entry_section_stub_is_directory():
    e = Entry.from_json({"path": "/my-files"})
    assert e.name == "my-files" and e.path == "/my-files" and e.is_dir is True


def test_entry_file_from_list_derives_path_from_parent():
    e = Entry.from_json(FILE_NODE, parent="/my-files")
    assert e.name == "kaas.txt"
    assert e.path == "/my-files/kaas.txt"
    assert e.is_dir is False
    assert e.size == 95
    assert e.uid == "ROOT~FILE"
    assert e.mtime == _parse_iso("2026-03-26T00:51:13.000Z")


def test_entry_folder_type():
    e = Entry.from_json(FOLDER_NODE, parent="/my-files")
    assert e.is_dir is True and e.size is None


def test_entry_info_uses_explicit_path_override():
    # `filesystem info /my-files` returns name "root"; the path override wins.
    info = {"uid": "ROOT~PARENT", "name": {"ok": True, "value": "root"},
            "type": "folder", "ownedBy": {"email": "m.beulens@syntec-one.nl"}}
    e = Entry.from_json(info, path="/my-files")
    assert e.name == "my-files" and e.path == "/my-files" and e.is_dir is True


def test_entry_undecryptable_name_falls_back_to_uid():
    node = {"uid": "ROOT~X", "name": {"ok": False}, "type": "file"}
    e = Entry.from_json(node, parent="/my-files")
    assert e.name == "ROOT~X"


def test_transfer_result_from_json():
    t = TransferResult.from_json(
        {"transferredItems": 1, "transferredBytes": 17,
         "skippedItems": 0, "failedItems": 0, "failures": []})
    assert t.transferred_items == 1 and t.transferred_bytes == 17
    assert t.skipped_items == 0 and t.failed_items == 0 and t.failures == []


def test_share_info_unshared_from_empty():
    s = ShareInfo.from_json({}, path="/my-files/kaas.txt")
    assert s.shared is False and s.members == [] and s.path == "/my-files/kaas.txt"


def test_auth_status_dataclass():
    a = AuthStatus(logged_in=True, account="user@pm.me")
    assert a.logged_in is True and a.account == "user@pm.me"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protondisk.core.models'`

- [ ] **Step 3: Write minimal implementation**

`protondisk/core/models.py`:
```python
"""Typed dataclasses parsed from `proton-drive --json` output (cli-drive 0.5.0).

All field-name knowledge lives here so reconciling with future CLI versions is local.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _unwrap(result) -> str | None:
    """Return the value of a `{"ok": bool, "value": ...}` Result wrapper."""
    if isinstance(result, dict) and result.get("ok"):
        return result.get("value")
    return None


def _parse_iso(s) -> float | None:
    """Parse an ISO-8601 timestamp (trailing Z allowed) to epoch seconds."""
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    if not stripped:
        return "/"
    return stripped.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    is_dir: bool
    size: int | None
    mtime: float | None
    uid: str | None

    @classmethod
    def from_json(cls, data: dict, *, path: str | None = None, parent: str = "") -> "Entry":
        # Top-level section stub from `list /`: {"path": "/my-files"}
        if "type" not in data and data.get("path"):
            p = data["path"]
            return cls(name=_basename(p), path=p, is_dir=True,
                       size=None, mtime=None, uid=None)
        decrypted = _unwrap(data.get("name"))
        if path is not None:
            node_path = path
            name = _basename(path)
        else:
            name = decrypted or data.get("uid", "")
            node_path = f"{parent.rstrip('/')}/{name}" if parent else "/" + name
        return cls(
            name=name,
            path=node_path,
            is_dir=data.get("type") == "folder",
            size=data.get("totalStorageSize"),
            mtime=_parse_iso(data.get("modificationTime")),
            uid=data.get("uid"),
        )


@dataclass(frozen=True)
class AuthStatus:
    logged_in: bool
    account: str | None


@dataclass(frozen=True)
class TransferResult:
    transferred_items: int
    transferred_bytes: int
    skipped_items: int
    failed_items: int
    failures: list

    @classmethod
    def from_json(cls, data: dict) -> "TransferResult":
        return cls(
            transferred_items=data.get("transferredItems", 0),
            transferred_bytes=data.get("transferredBytes", 0),
            skipped_items=data.get("skippedItems", 0),
            failed_items=data.get("failedItems", 0),
            failures=data.get("failures", []),
        )


@dataclass(frozen=True)
class ShareInfo:
    path: str
    shared: bool
    members: list[str]

    @classmethod
    def from_json(cls, data: dict, *, path: str = "") -> "ShareInfo":
        if not data:
            return cls(path=path, shared=False, members=[])
        members = [
            m.get("email", "") for m in data.get("members", []) if isinstance(m, dict)
        ]
        return cls(path=data.get("path", path), shared=True, members=members)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.7
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/models.py tests/test_models.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): typed models with real proton-drive JSON parsing (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 4: CLIRunner — discovery, execution, error mapping

**Files:**
- Create: `protondisk/core/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces:
  - `CLIRunner(binary=None)` — discover via `shutil.which("proton-drive")`; missing → `CLINotFoundError`.
  - `CLIRunner.run(*args, input_text=None) -> dict | list` — invokes `[binary, *args, "--json"]`. Non-zero exit → `map_error(...)` raised. On success, `stdout.strip()`: empty or `"undefined"` → `{}`; otherwise `json.loads`.
  - `map_error(returncode, stdout, stderr) -> ProtonDiskError` — message from JSON `{"error":{"message":…}}` in stdout else stderr else stdout; classify by keyword: `not found`/`no such`→`NotFoundError`; `login`/`unauthorized`/`not logged in`/`auth`→`AuthError`; `conflict`/`already exists`→`ConflictError`; `rate`/`throttl`/`429`→`RateLimitError`; else `ProtonDiskError`.

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
    ("Something weird happened", ProtonDiskError),
])
def test_map_error_classification(text, exc):
    err = map_error(1, "", text)
    assert isinstance(err, exc) and str(err)


def test_map_error_prefers_json_error_message():
    stdout = json.dumps({"error": {"message": "Rate limit hit, slow down"}})
    err = map_error(1, stdout, "")
    assert isinstance(err, RateLimitError) and "Rate limit" in str(err)
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
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
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
        if not stdout or stdout == "undefined":
            return {}
        return json.loads(stdout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.8
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/runner.py tests/test_runner.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): CLIRunner with discovery, undefined handling, error mapping (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 5: ProtonDisk façade — auth (probe-based)

**Files:**
- Create: `protondisk/core/client.py`
- Test: `tests/test_client_auth.py`

**Interfaces:**
- Consumes: `CLIRunner`, `AuthStatus`, `AuthError`.
- Produces:
  - `ProtonDisk(runner=None)` — stores injected runner; default `CLIRunner()`.
  - `auth_status() -> AuthStatus` — calls `runner.run("filesystem", "info", "/my-files")`; on `AuthError` returns `AuthStatus(False, None)`; else `AuthStatus(True, data.get("ownedBy", {}).get("email"))`.
  - `login() -> None` → `runner.run("auth", "login")`.
  - `logout() -> None` → `runner.run("auth", "logout")`.
- Test double `FakeRunner`: records `.calls`; each entry either returns a queued result or raises a queued exception.

- [ ] **Step 1: Write the failing test**

`tests/test_client_auth.py`:
```python
from protondisk.core.client import ProtonDisk
from protondisk.core.models import AuthStatus
from protondisk.core.errors import AuthError


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
        self.calls.append(args)
        if not self._results:
            return {}
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_auth_status_logged_in_reads_account_from_ownedBy():
    runner = FakeRunner([{"type": "folder", "ownedBy": {"email": "user@pm.me"}}])
    status = ProtonDisk(runner=runner).auth_status()
    assert status == AuthStatus(logged_in=True, account="user@pm.me")
    assert runner.calls[0] == ("filesystem", "info", "/my-files")


def test_auth_status_logged_out_on_auth_error():
    runner = FakeRunner([AuthError("You need to login first")])
    status = ProtonDisk(runner=runner).auth_status()
    assert status == AuthStatus(logged_in=False, account=None)


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
from .errors import AuthError, NotFoundError
from .models import AuthStatus, Entry, TransferResult, ShareInfo


class ProtonDisk:
    ROOT = "/my-files"

    def __init__(self, runner: CLIRunner | None = None) -> None:
        self._runner = runner or CLIRunner()

    # --- auth ---
    def auth_status(self) -> AuthStatus:
        try:
            data = self._runner.run("filesystem", "info", self.ROOT)
        except AuthError:
            return AuthStatus(logged_in=False, account=None)
        account = data.get("ownedBy", {}).get("email") if isinstance(data, dict) else None
        return AuthStatus(logged_in=True, account=account)

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
ver=$(scripts/bump-patch.sh)   # -> 0.1.9
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_auth.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): probe-based auth_status, login, logout (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 6: ProtonDisk façade — browsing (list, stat)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_browse.py`

**Interfaces:**
- Produces (added to `ProtonDisk`):
  - `list(path: str) -> list[Entry]` → `runner.run("filesystem", "list", path)` returns a JSON **array**; each item → `Entry.from_json(item, parent=path)`. If the runner returns a non-list (e.g. `{}`), return `[]`.
  - `stat(path: str) -> Entry` → `runner.run("filesystem", "info", path)` → `Entry.from_json(data, path=path)`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_browse.py`:
```python
from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_browse.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'list'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- browsing ---
    def list(self, path: str) -> list[Entry]:
        data = self._runner.run("filesystem", "list", path)
        if not isinstance(data, list):
            return []
        return [Entry.from_json(item, parent=path) for item in data]

    def stat(self, path: str) -> Entry:
        data = self._runner.run("filesystem", "info", path)
        return Entry.from_json(data, path=path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_browse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.10
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_browse.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): browsing methods list and stat (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 7: ProtonDisk façade — transfer (upload, download)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_transfer.py`

**Interfaces:**
- Produces (added to `ProtonDisk`):
  - `upload(local: str, parent: str, *, conflict: str = "skip") -> TransferResult` → `runner.run("filesystem", "upload", "--conflict-strategy", conflict, local, parent)`.
  - `download(remote: str, local_folder: str) -> TransferResult` → `runner.run("filesystem", "download", remote, local_folder)`.
  - Both parse with `TransferResult.from_json`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_transfer.py`:
```python
from protondisk.core.client import ProtonDisk

TRANSFER = {"transferredItems": 1, "transferredBytes": 17,
            "skippedItems": 0, "failedItems": 0, "failures": []}


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_transfer.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'upload'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- transfer ---
    def upload(self, local: str, parent: str, *, conflict: str = "skip") -> TransferResult:
        data = self._runner.run(
            "filesystem", "upload", "--conflict-strategy", conflict, local, parent)
        return TransferResult.from_json(data)

    def download(self, remote: str, local_folder: str) -> TransferResult:
        data = self._runner.run("filesystem", "download", remote, local_folder)
        return TransferResult.from_json(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_transfer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.11
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_transfer.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): transfer methods upload and download (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 8: ProtonDisk façade — organize (mkdir, rename, move, trash)

**Files:**
- Modify: `protondisk/core/client.py`
- Test: `tests/test_client_organize.py`

**Interfaces:**
- Produces (added to `ProtonDisk`):
  - `mkdir(path: str) -> None` — split `path` into `parent`/`name` on the last `/`; → `runner.run("filesystem", "create-folder", parent, name)`.
  - `rename(path: str, new_name: str) -> None` → `runner.run("filesystem", "rename", path, new_name)`.
  - `move(src: str, target_parent: str) -> None` → `runner.run("filesystem", "move", src, target_parent)`.
  - `trash(path: str) -> None` → `runner.run("filesystem", "trash", path)`.

- [ ] **Step 1: Write the failing test**

`tests/test_client_organize.py`:
```python
from protondisk.core.client import ProtonDisk


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])

    def run(self, *args, input_text=None):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_organize.py -v`
Expected: FAIL — `AttributeError: 'ProtonDisk' object has no attribute 'mkdir'`

- [ ] **Step 3: Write minimal implementation**

Append inside the `ProtonDisk` class in `protondisk/core/client.py`:
```python
    # --- organize ---
    def mkdir(self, path: str) -> None:
        parent, _, name = path.rstrip("/").rpartition("/")
        self._runner.run("filesystem", "create-folder", parent or "/", name)

    def rename(self, path: str, new_name: str) -> None:
        self._runner.run("filesystem", "rename", path, new_name)

    def move(self, src: str, target_parent: str) -> None:
        self._runner.run("filesystem", "move", src, target_parent)

    def trash(self, path: str) -> None:
        self._runner.run("filesystem", "trash", path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_organize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.12
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py tests/test_client_organize.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): organize methods mkdir rename move trash (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 9: ProtonDisk façade — sharing + public exports  ⚠️ VERSION 13 SKIP

> **This task's bump lands on patch 13**, so `scripts/bump-patch.sh` jumps 0.1.13 → **0.1.14** and prints the skip notice. **Per project rule, this commit's message MUST be `To be sure to be sure!`** (the feature is described in the commit body).

**Files:**
- Modify: `protondisk/core/client.py`
- Modify: `protondisk/core/__init__.py`
- Test: `tests/test_client_sharing.py`

**Interfaces:**
- Produces (added to `ProtonDisk`):
  - `sharing_status(path: str) -> ShareInfo` → `ShareInfo.from_json(runner.run("sharing", "status", path), path=path)` (unshared `{}` → not shared).
  - `sharing_invite(path: str, user: str, role: str = "viewer", message: str = "") -> None` → argv `["sharing", "invite", "--user", user, "--role", role]` + (`["--message", message]` only if `message`) + `[path]`.
- `protondisk/core/__init__.py` re-exports `ProtonDisk`, all models, all errors.

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


def test_sharing_status_unshared_returns_not_shared():
    runner = FakeRunner([{}])  # runner maps `undefined` -> {}
    info = ProtonDisk(runner=runner).sharing_status("/my-files/kaas.txt")
    assert isinstance(info, ShareInfo)
    assert info.shared is False and info.members == []
    assert runner.calls[0] == ("sharing", "status", "/my-files/kaas.txt")


def test_sharing_invite_with_message_passes_all_flags():
    runner = FakeRunner()
    ProtonDisk(runner=runner).sharing_invite(
        "/my-files/Reports", "b@pm.me", role="editor", message="pls review")
    assert runner.calls[0] == (
        "sharing", "invite", "--user", "b@pm.me", "--role", "editor",
        "--message", "pls review", "/my-files/Reports")


def test_sharing_invite_omits_empty_message_and_defaults_viewer():
    runner = FakeRunner()
    ProtonDisk(runner=runner).sharing_invite("/my-files/Reports", "b@pm.me")
    assert runner.calls[0] == (
        "sharing", "invite", "--user", "b@pm.me", "--role", "viewer",
        "/my-files/Reports")


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
        data = self._runner.run("sharing", "status", path)
        return ShareInfo.from_json(data, path=path)

    def sharing_invite(self, path: str, user: str, role: str = "viewer",
                       message: str = "") -> None:
        args = ["sharing", "invite", "--user", user, "--role", role]
        if message:
            args += ["--message", message]
        args.append(path)
        self._runner.run(*args)
```

Replace `protondisk/core/__init__.py` with:
```python
"""ProtonDisk core: typed wrapper around the official proton-drive CLI."""
from .client import ProtonDisk
from .models import Entry, AuthStatus, TransferResult, ShareInfo
from .errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
)

__all__ = [
    "ProtonDisk", "Entry", "AuthStatus", "TransferResult", "ShareInfo",
    "ProtonDiskError", "CLINotFoundError", "AuthError",
    "NotFoundError", "ConflictError", "RateLimitError",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client_sharing.py -v`
Expected: PASS

- [ ] **Step 5: Commit (VERSION 13 SKIP — special message)**

```bash
ver=$(scripts/bump-patch.sh)   # 0.1.13 -> skipped to 0.1.14 (prints skip notice to stderr)
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/core/client.py protondisk/core/__init__.py tests/test_client_sharing.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "To be sure to be sure! (v$ver)

feat(core): sharing methods (sharing_status, sharing_invite) and public core exports.
Patch version 0.1.13 skipped per project rule.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

### Task 10: Thin `protondisk` CLI entrypoint

**Files:**
- Create: `protondisk/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `main(argv: list[str] | None = None, disk: ProtonDisk | None = None) -> int` — argparse with subcommands `version`, `auth-status`, `ls PATH`. `disk` injectable (default `ProtonDisk()`). `version` prints `__version__` without constructing a disk. On `ProtonDiskError`, prints `error: <msg>` to stderr and returns `1`; else `0`.

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
    assert main(["version"]) == 0
    assert protondisk.__version__ in capsys.readouterr().out


def test_auth_status_prints_account(capsys):
    disk = FakeDisk(status=AuthStatus(logged_in=True, account="user@pm.me"))
    assert main(["auth-status"], disk=disk) == 0
    assert "user@pm.me" in capsys.readouterr().out


def test_ls_lists_entries(capsys):
    disk = FakeDisk(entries=[
        Entry("Reports", "/my-files/Reports", True, None, None, "U1"),
        Entry("q3.pdf", "/my-files/q3.pdf", False, 10, None, "U2"),
    ])
    assert main(["ls", "/my-files"], disk=disk) == 0
    out = capsys.readouterr().out
    assert "Reports" in out and "q3.pdf" in out


def test_error_returns_1_and_prints_stderr(capsys):
    disk = FakeDisk(error=AuthError("not logged in"))
    assert main(["auth-status"], disk=disk) == 1
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
            print(f"logged in as {status.account}" if status.logged_in else "not logged in")
        elif args.command == "ls":
            for entry in disk.list(args.path):
                print(f"{'/' if entry.is_dir else ' '} {entry.name}")
    except ProtonDiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python -m pytest tests/ -v`
Expected: PASS (all suites)

Optional live smoke test (requires a logged-in session; not for CI):
Run: `python -m protondisk.cli auth-status` → prints `logged in as <account>`
Run: `python -m protondisk.cli ls /my-files` → lists your Drive root

- [ ] **Step 5: Commit**

```bash
ver=$(scripts/bump-patch.sh)   # -> 0.1.15
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  add protondisk/cli.py tests/test_cli.py VERSION
git -c user.name='mbeulens' -c user.email='m.beulens@syntec-it.nl' \
  commit -m "feat(core): thin protondisk CLI entrypoint (v$ver)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin dev
```

---

## Milestone Completion — "Bump minor" to 0.2.0

After all 10 tasks pass, when the user says **"Bump minor"**, do:

1. Create/update `CHANGELOG.md` documenting the 0.2.0 core release.
2. Update `README.md` (install prerequisites: `proton-drive` binary + Python 3.12; `protondisk` usage; core API overview).
3. Set `VERSION` to `0.2.0`.
4. Commit to `dev`, merge `dev` → `main`, push both branches.

---

## Self-Review

**1. Spec coverage (Milestone 1 scope, per design doc §4 + §12):**
- Core API auth/list/stat/upload/download/mkdir/rename/move/trash/sharing → Tasks 5–9 ✅
- `CLIRunner` (discovery, JSON/undefined/empty handling, error mapping) → Task 4 ✅
- Typed dataclasses with real shapes (Result-wrapped names, ISO times, uid, transfer fields) → Task 3 ✅
- Error hierarchy (6 classes) → Task 2 ✅
- Probe-based `auth_status` reading `ownedBy.email` → Task 5 ✅
- Fake-runner testing, no account needed → every task ✅
- `protondisk/cli.py` → Task 10 ✅
- Packaging + VERSION-driven version + bump script → Task 1 ✅
- Versioning rule incl. 13-skip with `To be sure to be sure!` → Task 9 ✅
- GUI, mount, config file → deferred to later milestones ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. ✅

**3. Type consistency:** `ProtonDisk`, `CLIRunner`, `map_error`, `Entry/TransferResult/ShareInfo.from_json`, `AuthStatus`, and `FakeRunner.run(*args, input_text=None)` are consistent across tasks. Method names match §12 (`auth_status`, `stat`, `mkdir`, `rename`, `move`, `trash`, `sharing_status`, `sharing_invite`). `Entry` fields (`name/path/is_dir/size/mtime/uid`) are consistent everywhere. ✅

**Remaining live-only unknown:** the JSON shape of `sharing status` for a *shared* node (the shared root errored on decrypt during capture). `ShareInfo.from_json` handles the unshared case exactly; the shared-node member list is best-effort until captured against a genuinely shared node. Flagged here; localized to `ShareInfo`.

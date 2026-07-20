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

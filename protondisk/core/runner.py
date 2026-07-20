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

"""The only module that invokes the proton-drive binary."""
from __future__ import annotations

import json
import shutil
import subprocess

from .errors import (
    ProtonDiskError, CLINotFoundError, AuthError,
    NotFoundError, ConflictError, RateLimitError,
)
from .progress import strip_ansi

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
    if "rate" in lowered or "throttl" in lowered or "429" in lowered or "too many" in lowered:
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

    def run_streaming(self, *args: str, on_line=None) -> dict | list:
        """Run a command, streaming each output line to `on_line` as it arrives.

        Used with `--verbose` (pass it in *args): the CLI interleaves verbose log
        lines with the final `--json` result on stdout. Each raw line is handed to
        `on_line`; the return value is the last line that parses as JSON (the
        result), or `{}` if none. stderr is merged into stdout so a failure's
        message is captured for `map_error`.
        """
        cmd = [self.binary, *args, "--json"]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        result: dict | list = {}
        lines: list[str] = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line is not None:
                on_line(line)
            stripped = strip_ansi(line).strip()
            if stripped[:1] in ("{", "["):
                try:
                    result = json.loads(stripped)
                except ValueError:
                    pass
        proc.wait()
        if proc.returncode != 0:
            tail = [s for s in (strip_ansi(x).strip() for x in lines) if s]
            raise map_error(proc.returncode, "", "\n".join(tail[-3:]))
        return result

"""Map `proton-drive --verbose` log lines to short, human-readable transfer phases.

With `--verbose`, the CLI streams ANSI-coloured log lines to stdout during a
transfer (mixed with the final --json result). Each line looks like:

    2026-07-20T02:22:27Z INFO [upload] revision …: Encrypting block 1

`parse_progress_line` returns a short phase label for `[upload]`/`[download]`
lines and ``None`` for everything else (`[api]`, `[metric]`, `[cli]`, …). We key
off the component + message wording rather than the `[metric] performance`
lines, because an upload emits both content_encryption AND content_decryption
(verification) metrics, which would otherwise mislabel the phase.
"""
from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_COMPONENT = re.compile(r"\[(upload|download)\]")


def strip_ansi(line: str) -> str:
    return _ANSI.sub("", line)


def parse_progress_line(raw: str) -> str | None:
    """Return a phase label (e.g. "Encrypting…") for a verbose line, or None."""
    line = strip_ansi(raw)
    match = _COMPONENT.search(line)
    if not match:
        return None
    component = match.group(1)
    msg = line[match.end():].lower()

    if component == "upload":
        if "encrypting" in msg:
            return "Encrypting…"
        if "starting upload" in msg or "generating file crypto" in msg:
            return "Starting…"
        if "committing" in msg or "succeeded" in msg or "cleanup" in msg or "uploaded" in msg:
            return "Finishing…"
        if "uploading" in msg or "upload started" in msg or "requesting upload tokens" in msg:
            return "Uploading…"
        return None

    # component == "download"
    if "decrypting" in msg:
        return "Decrypting…"
    if "verifying" in msg:
        return "Verifying…"
    if "starting download" in msg:
        return "Starting…"
    if "succeeded" in msg or "cleanup" in msg or "flushing" in msg or "downloaded" in msg:
        return "Finishing…"
    if "downloading" in msg or "download started" in msg:
        return "Downloading…"
    return None

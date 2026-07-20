"""Tests for progress-line parsing, using REAL captured proton-drive verbose lines."""
from protondisk.core.progress import parse_progress_line, strip_ansi


def test_strip_ansi():
    assert strip_ansi("\x1b[1;34mhello\x1b[0m") == "hello"
    assert strip_ansi("plain") == "plain"


def test_upload_phases_from_real_lines():
    assert parse_progress_line(
        "2026 INFO [upload] Generating file crypto with AEAD enabled") == "Starting…"
    assert parse_progress_line(
        "2026 INFO [upload] revision X: Starting upload") == "Starting…"
    assert parse_progress_line(
        "\x1b[1;90m2026 DEBUG [upload] revision X: Encrypting block 1\x1b[0m") == "Encrypting…"
    assert parse_progress_line(
        "2026 INFO [upload] revision X: Requesting upload tokens for 2 blocks") == "Uploading…"
    assert parse_progress_line(
        "2026 INFO [upload] revision X: block 1:JWT: Upload started") == "Uploading…"
    assert parse_progress_line(
        "2026 DEBUG [upload] revision X: block 1:JWT: Uploading") == "Uploading…"
    assert parse_progress_line(
        "2026 DEBUG [upload] revision X: All blocks uploaded, committing") == "Finishing…"
    assert parse_progress_line(
        "2026 INFO [upload] revision X: Upload succeeded") == "Finishing…"


def test_download_phases_from_real_lines():
    assert parse_progress_line(
        "2026 INFO [download] revision X: Starting download") == "Starting…"
    assert parse_progress_line(
        "2026 INFO [download] revision X: block 1: Download started") == "Downloading…"
    assert parse_progress_line(
        "2026 DEBUG [download] revision X: block 1: Downloading") == "Downloading…"
    assert parse_progress_line(
        "2026 DEBUG [download] revision X: block 1: Verifying hash") == "Verifying…"
    assert parse_progress_line(
        "2026 DEBUG [download] revision X: block 1: Decrypting") == "Decrypting…"
    assert parse_progress_line(
        "2026 INFO [download] revision X: Download succeeded") == "Finishing…"


def test_noise_lines_return_none():
    # metric / api / cli / crypto components are not transfer phases
    assert parse_progress_line(
        '2026 INFO [metric] performance {"type":"content_decryption","bytesProcessed":4000000}') is None
    assert parse_progress_line(
        "2026 DEBUG [api] POST https://drive-api.proton.me/drive/blocks") is None
    assert parse_progress_line(
        "2026 DEBUG [cli] Loading session auth-session from secrets") is None
    assert parse_progress_line(
        "2026 DEBUG [nodes-crypto] Node X decrypted in 11ms") is None
    assert parse_progress_line('{"transferredItems":1,"transferredBytes":30}') is None


def test_upload_decryption_metric_does_not_mislabel():
    # An upload emits a content_decryption metric (verification); it must NOT
    # be read as a "Decrypting…" phase.
    line = '2026 INFO [metric] performance {"type":"content_decryption","bytesProcessed":3000000}'
    assert parse_progress_line(line) is None
